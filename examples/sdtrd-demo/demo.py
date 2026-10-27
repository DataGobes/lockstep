"""Lockstep on an SDTRD repo: five PRs, what each check says about them.

Builds a project with SDTRD's own ``sdtrd init`` and templates, adds Lockstep with the SDTRD profile
(templates/sdtrd/lockstep.toml, set to enforce), then opens five PRs as git branches and runs the checks on each
the way the GitHub Actions workflow does. Nothing is added to the project's specs/ beyond what SDTRD itself writes.

  python examples/sdtrd-demo/demo.py [--sdtrd <SDTRD checkout>] [--keep <dir>]

Without --sdtrd it clones github.com/mgabs/SDTRD at the commit the profile was built against. Exits 1 if any PR
gets a different verdict than the one the demo expects.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LOCKSTEP = Path(__file__).resolve().parents[2]
SDTRD_URL = "https://github.com/mgabs/SDTRD"
SDTRD_COMMIT = "6187aca"
CHECKS = ("spec_required", "ac_traceability", "test_tamper", "pr_size", "team_rules")
FEATURE = "specs/features/w1.1-token-check"
SHIPPED = "specs/archive/w1.0-tokens-basic"


@dataclass
class Pr:
    branch: str
    title: str
    story: str
    files: dict[str, str]
    blocked_by: tuple[str, ...] = ()  # the checks that should fail; every other check should pass
    base_files: dict[str, str] = field(default_factory=dict)  # committed to main before the PR branches off


def spec(gate2: bool, reqs: list[tuple[str, str]], template: str) -> str:
    """SDTRD's spec template with real keys in place of its placeholders."""
    lines = [f"- **{key} ({name})**: The system MUST {name.lower()}." for key, name in reqs]
    text = re.sub(
        r"### 1\. Functional Requirements\n\n(?:- .*\n)+",
        "### 1. Functional Requirements\n\n" + "\n".join(lines) + "\n",
        template,
    )
    text = re.sub(
        r"### 2\. Non-Functional Requirements & Budgets\n\n(?:- .*\n)+",
        "### 2. Non-Functional Requirements & Budgets\n\n",
        text,
    )
    text = text.replace("ASM-<DOMAIN>-1", "ASM-AUTH-1")
    return text.replace("- [ ] **Gate 2", "- [x] **Gate 2") if gate2 else text


def tasks(gate4: bool, gate6: bool, template: str) -> str:
    text = template.replace("- [ ] **Gate 4", "- [x] **Gate 4") if gate4 else template
    return text.replace("- [ ] **Gate 6", "- [x] **Gate 6") if gate6 else text


def scenarios(t: dict[str, str]) -> list[Pr]:
    reqs = [("REQ-AUTH-1", "Reject an empty token"), ("REQ-AUTH-2", "Reject an expired token")]
    code = {"src/tokens.py": "def check(token, expired=False):\n    return bool(token) and not expired\n"}
    tested = {
        "tests/bdd/features/tokens.feature": (
            "Feature: Token check\n\n  @REQ-AUTH-1\n  Scenario: An empty token is rejected\n\n"
            "  @REQ-AUTH-2\n  Scenario: An expired token is rejected\n"
        )
    }
    shipped = {
        f"{SHIPPED}/specs/tokens/spec.md": spec(True, [("REQ-TOK-1", "Parse a token")], t["spec"]),
        f"{SHIPPED}/tasks.md": tasks(True, True, t["tasks"]),
        "specs/living/tokens/spec.md": spec(True, [("REQ-TOK-1", "Parse a token")], t["spec"]),
        "src/parse.py": "def parse(raw):\n    return raw.strip()\n",
        "tests/test_parse.py": "def test_parse():  # REQ-TOK-1\n    assert parse(' a ') == 'a'\n",
    }
    return [
        Pr(
            "feat/w1.1-token-check",
            "Token check",
            "Code before the tasks are approved: Gate 2 ticked, Gate 4 not.",
            {
                f"{FEATURE}/specs/tokens/spec.md": spec(True, reqs, t["spec"]),
                f"{FEATURE}/tasks.md": tasks(False, False, t["tasks"]),
                **code,
            },
            ("spec_required",),
            shipped,
        ),
        Pr(
            "feat/w1.1-token-check",
            "Token check",
            "Into main with Gate 4 ticked, one requirement untested and Gate 6 not ticked.",
            {
                f"{FEATURE}/specs/tokens/spec.md": spec(True, reqs, t["spec"]),
                f"{FEATURE}/tasks.md": tasks(True, False, t["tasks"]),
                **code,
                "tests/bdd/features/tokens.feature": tested["tests/bdd/features/tokens.feature"].split(
                    "\n  @REQ-AUTH-2"
                )[0]
                + "\n",
            },
            ("spec_required", "ac_traceability"),
            shipped,
        ),
        Pr(
            "feat/w1.1-token-check",
            "Token check",
            "Same feature, but the agent loosened a shipped test to make its change pass.",
            {
                f"{FEATURE}/specs/tokens/spec.md": spec(True, reqs, t["spec"]),
                f"{FEATURE}/tasks.md": tasks(True, True, t["tasks"]),
                **code,
                **tested,
                "tests/test_parse.py": "def test_parse():  # REQ-TOK-1\n    assert parse(' a ')\n",
            },
            ("test_tamper",),
            shipped,
        ),
        Pr(
            "fix/empty-token-crash",
            "Fix crash on empty token",
            "A bug fix whose report is not triaged yet (Gate B1 open).",
            {
                "specs/bug-reports/2026-10-27-empty-token-crash.md": t["bug-report"],
                "src/parse.py": "def parse(raw):\n    return (raw or '').strip()\n",
                "tests/test_parse_empty.py": "def test_parse_none():  # REQ-TOK-1\n    assert parse(None) == ''\n",
            },
            ("spec_required",),
            shipped,
        ),
        Pr(
            "feat/w1.1-token-check",
            "Token check",
            "The feature done the SDTRD way: gates 2, 4 and 6 ticked, every requirement tested.",
            {
                f"{FEATURE}/specs/tokens/spec.md": spec(True, reqs, t["spec"]),
                f"{FEATURE}/tasks.md": tasks(True, True, t["tasks"]),
                **code,
                **tested,
            },
            (),
            shipped,
        ),
    ]


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def project(sdtrd: Path, where: Path) -> Path:
    """An empty SDTRD project (sdtrd init) with Lockstep added, committed on main."""
    root = where / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "demo@example.invalid")
    git(root, "config", "user.name", "Lockstep demo")
    subprocess.run(["sh", str(sdtrd / "bin" / "sdtrd"), "init", str(root)], check=True, capture_output=True)
    shutil.copytree(LOCKSTEP / "core" / "src", root / ".lockstep" / "src", ignore=shutil.ignore_patterns("__pycache__"))
    profile = (LOCKSTEP / "templates" / "sdtrd" / "lockstep.toml").read_text(encoding="utf-8")
    write(root, {"lockstep.toml": profile.replace('default = "warn"', 'default = "enforce"')})
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", "sdtrd init + Lockstep")  # SDTRD's hook forbids commits on main
    return root


def run_checks(root: Path, pr: Pr) -> dict[str, list[str]]:
    env = {
        **os.environ,
        "PYTHONPATH": str(root / ".lockstep" / "src"),
        "GITHUB_ACTIONS": "",  # plain output, not annotations
        "GITHUB_BASE_REF": "main",
        "GITHUB_HEAD_REF": pr.branch,
        "LOCKSTEP_PR_TITLE": pr.title,
    }
    results = {}
    for check in CHECKS:
        p = subprocess.run(
            [sys.executable, "-m", f"lockstep_checks.check_{check}", "--base", "main"],
            check=False,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        lines = [line for line in p.stdout.splitlines() if line.startswith(("ERROR", "WARNING"))]
        results[check] = ["FAIL" if p.returncode else "ok", *lines]
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sdtrd", type=Path, help="an SDTRD checkout (default: clone it)")
    ap.add_argument("--keep", type=Path, help="build the projects here and keep them")
    args = ap.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="sdtrd-demo-")) if args.keep is None else args.keep.resolve()
    work.mkdir(parents=True, exist_ok=True)
    sdtrd = args.sdtrd.resolve() if args.sdtrd else None
    if sdtrd is None:
        sdtrd = work / "SDTRD"
        subprocess.run(["git", "clone", "-q", SDTRD_URL, str(sdtrd)], check=True)
        git(sdtrd, "checkout", "-q", SDTRD_COMMIT)
    templates = {
        name: (sdtrd / "templates" / f"{name}.md").read_text(encoding="utf-8")
        for name in ("spec", "tasks", "bug-report")
    }

    surprises = 0
    for n, pr in enumerate(scenarios(templates), start=1):
        where = work / f"pr{n}"
        where.mkdir()
        root = project(sdtrd, where)
        write(root, pr.base_files)
        git(root, "add", "-A")
        git(root, "commit", "-q", "--no-verify", "-m", "w1.0 shipped")
        git(root, "checkout", "-q", "-b", pr.branch)
        write(root, pr.files)
        git(root, "add", "-A")
        git(root, "commit", "-q", "--no-verify", "-m", pr.title)
        results = run_checks(root, pr)
        failed = tuple(c for c, r in results.items() if r[0] == "FAIL")
        verdict = "BLOCKED" if failed else "PASSES"
        expected = failed == pr.blocked_by
        surprises += not expected
        print(f"\nPR {n}: {pr.branch} -> main  [{verdict}{'' if expected else ', NOT AS EXPECTED'}]")
        print(f"  {pr.story}")
        for check, (state, *lines) in results.items():
            print(f"  {state:4}  {check}")
            for line in lines:
                print(f"        {line}")
    print(f"\nProjects in {work}" if args.keep else "")
    return 1 if surprises else 0


if __name__ == "__main__":
    sys.exit(main())
