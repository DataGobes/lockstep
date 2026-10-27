#!/usr/bin/env python3
"""Facts about a repo, for seeding its workflow. Reads files and git history; changes nothing.

  python3 probe.py --root <repo> [--json]

Prints a profile: signals (short names the catalogue matches on), the commands the agent will need, and team
figures from the last 90 days of git history. Judgement stays with the agent and the team.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "target",
    "dist",
    "build",
    ".workflow",
    ".lockstep",
}
MAX_FILES = 20000
LANGS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".sql": "sql",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".scala": "scala",
    ".ipynb": "notebook",
}
LLM_SDKS = ("anthropic", "openai", "langchain", "llama_index", "llama-index", "semantic-kernel", "azure-ai-inference")
DEPLOY_FILES = {
    "databricks.yml": "databricks",
    "main.tf": "terraform",
    "Chart.yaml": "helm",
    "serverless.yml": "serverless",
    "bicepconfig.json": "bicep",
}
SECRET_NAMES = re.compile(r"^(\.env(\..+)?|.*\.pem|.*\.pfx|secrets?\.(json|ya?ml|toml))$")


def walk(root: Path) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    while stack and len(found) < MAX_FILES:
        folder = stack.pop()
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in SKIP_DIRS:
                    stack.append(e)
            else:
                found.append(e)
    return found


def git(root: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout if p.returncode == 0 else ""


def history(root: Path, days: int = 90) -> dict:
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    log = git(root, "log", f"--since={since}", "--no-merges", "--format=%ae%x09%s")
    rows = [line.split("\t", 1) for line in log.splitlines() if "\t" in line]
    subjects = [s for _, s in rows]
    return {
        "days": days,
        "commits": len(rows),
        "contributors": len({a.lower() for a, _ in rows}),
        "reverts": sum(1 for s in subjects if s.startswith("Revert ")),
        "fix_commits": sum(1 for s in subjects if re.match(r"(?i)^(fix|hotfix|bugfix)\b|^\w+ fix\b", s)),
        "test_changes": sum(1 for s in subjects if "[test-change]" in s),
    }


def _read(p: Path, limit: int = 200_000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def probe(root: Path) -> dict:
    root = root.resolve()
    files = walk(root)
    rel = {f.relative_to(root).as_posix(): f for f in files}
    names = {Path(r).name for r in rel}
    signals: set[str] = set()
    commands: dict[str, str] = {}
    langs: dict[str, int] = {}
    for r in rel:
        lang = LANGS.get(Path(r).suffix)
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    for lang in langs:
        signals.add(f"lang_{lang}")

    # Python and its test runner
    pyproject = _read(root / "pyproject.toml") if "pyproject.toml" in rel else ""
    uv = "uv.lock" in rel
    has_tests_dir = any(r.startswith(("tests/", "test/")) or "/tests/" in r for r in rel)
    py_tests = any(re.match(r"(.*/)?test_[^/]+\.py$", r) for r in rel)
    if "pytest" in pyproject or py_tests:
        signals.add("pytest")
        commands["test"] = "uv run pytest" if uv else "python -m pytest"
    if "ruff" in pyproject:
        commands["lint"] = "uv run ruff check ." if uv else "ruff check ."

    # JavaScript / TypeScript
    if "package.json" in rel:
        try:
            pkg = json.loads(_read(root / "package.json"))
        except json.JSONDecodeError:
            pkg = {}
        scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
        runner = "pnpm" if "pnpm-lock.yaml" in rel else "yarn" if "yarn.lock" in rel else "npm run"
        for key in ("test", "lint", "build"):
            if key in scripts and key not in commands:
                commands[key] = f"{runner} {key}"
        deps = json.dumps(pkg.get("dependencies", {})) + json.dumps(pkg.get("devDependencies", {}))
        for t in ("jest", "vitest", "playwright"):
            if t in deps:
                signals.add(t)
        if any(s in deps for s in LLM_SDKS):
            signals.add("llm_sdk")

    # Data stack
    if "dbt_project.yml" in names:
        signals.add("dbt")
        commands.setdefault("build", "dbt build --select state:modified+")
    for fname, tool in DEPLOY_FILES.items():
        if fname in names:
            signals.add(tool)
            signals.add("deploy_cli")
    if "databricks" in signals:
        text = _read(root / "databricks.yml")
        if re.search(r"(?m)^\s+prod(uction)?:", text):
            signals.add("prod_target")
    if any(r.endswith(".tf") for r in rel):
        signals.add("terraform")
        signals.add("deploy_cli")

    # AI stack
    if any(s in pyproject for s in LLM_SDKS) or any(s in _read(root / "requirements.txt") for s in LLM_SDKS):
        signals.add("llm_sdk")
    if any(r.startswith(("evals/", "eval/")) or "/evals/" in r for r in rel):
        signals.add("evals")
    if any(r.startswith("prompts/") or r.endswith(".prompt.md") for r in rel):
        signals.add("prompts")

    # Secrets and data samples in the tree
    if any(SECRET_NAMES.match(Path(r).name) and not r.endswith(".example") for r in rel):
        signals.add("secret_files")
    if any(r.startswith(("data/samples/", "data/raw/")) for r in rel):
        signals.add("data_samples")

    # CI and agent tools
    if any(r.startswith(".github/workflows/") for r in rel):
        signals.add("ci_github")
    if any(Path(r).name.startswith("azure-pipelines") for r in rel) or any(r.startswith(".azuredevops/") for r in rel):
        signals.add("ci_ado")
    if "CLAUDE.md" in rel or ".claude/settings.json" in rel:
        signals.add("agent_claude")
    if ".github/copilot-instructions.md" in rel or any(r.startswith(".github/instructions/") for r in rel):
        signals.add("agent_copilot")
    if "AGENTS.md" in rel:
        signals.add("agents_md")
    if (root / ".lockstep").is_dir():
        signals.add("lockstep")
    if has_tests_dir or py_tests:
        signals.add("has_tests")
    else:
        signals.add("no_tests")
    if (root / "specs").is_dir():
        signals.add("specs")

    team = history(root)
    if team["contributors"] <= 3:
        signals.add("team_small")
    elif team["contributors"] >= 8:
        signals.add("team_large")
    agents_md_lines = len(_read(root / "AGENTS.md").splitlines()) if "AGENTS.md" in rel else 0
    return {
        "probed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo": root.name,
        "files": len(files),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "signals": sorted(signals),
        "commands": commands,
        "history": team,
        "agents_md_lines": agents_md_lines,
        "pyproject_name": tomllib.loads(pyproject).get("project", {}).get("name") if pyproject else None,
    }


def render(profile: dict) -> str:
    h = profile["history"]
    out = [
        f"Repo {profile['repo']}: {profile['files']} files",
        "Languages: " + (", ".join(f"{k} ({v})" for k, v in profile["languages"].items()) or "none found"),
        "Signals:   " + ", ".join(profile["signals"]),
        "Commands:  " + (", ".join(f"{k}: `{v}`" for k, v in profile["commands"].items()) or "none found"),
        (
            f"Last {h['days']} days: {h['commits']} commits by {h['contributors']} people; "
            f"{h['reverts']} reverts, {h['fix_commits']} fix commits, {h['test_changes']} [test-change] commits"
        ),
    ]
    if profile["agents_md_lines"]:
        out.append(f"AGENTS.md exists: {profile['agents_md_lines']} lines")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--json", action="store_true", help="print the profile as JSON")
    args = ap.parse_args(argv)
    if not args.root.is_dir():
        print(f"probe: {args.root} is not a folder", file=sys.stderr)
        return 2
    try:
        profile = probe(args.root)
    except tomllib.TOMLDecodeError as e:
        print(f"probe: pyproject.toml is not valid TOML: {e}", file=sys.stderr)
        return 2
    print(json.dumps(profile, indent=2) if args.json else render(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
