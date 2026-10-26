#!/usr/bin/env python3
"""Say where each spec is in the Lockstep flow and which skill comes next.

  python3 next_step.py --root <repo> [--base origin/main] [--json]

A spec's phase comes from its status.yml on its feature branch if it has one (the test PR merges there, so red tests
never reach main), else on the base branch (what is merged), else from the working tree for a spec that isn't merged
yet, plus the branches that exist for it: spec/, test/, feature/ or baseline/<id>-<slug>. Stdlib only; reads the
specs with the core in .lockstep/src.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

PREFIXES = ("spec", "test", "feature", "baseline")


@dataclass
class Step:
    spec: str
    status: str
    pii: bool
    branches: list[str]
    next: str
    skill: str | None


def load_core(root: Path):
    if not (root / ".lockstep" / "src" / "lockstep_checks").is_dir():
        return None
    sys.path.insert(0, str(root / ".lockstep" / "src"))
    try:
        from lockstep_checks import config, lock, spec, status
    except ImportError:
        return None
    finally:
        sys.path.pop(0)
    return config, lock, spec, status


def git(root: Path, *args: str) -> str | None:
    p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def spec_branches(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    refs = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes/origin") or ""
    for ref in refs.split():
        name = ref.removeprefix("origin/")
        m = re.match(rf"({'|'.join(PREFIXES)})/(\d+)-", name)
        if m and name not in found.get(m[2], []):
            found.setdefault(m[2], []).append(name)
    return found


def decide(
    status: str, branches: list[str], implementing: bool = False, baseline: bool = False
) -> tuple[str, str | None]:
    has = {b.split("/")[0] for b in branches}
    if baseline and status in ("draft", "approved"):
        if "baseline" in has:
            return (
                "baseline in progress: pin each criterion with a test that passes today, then open the PR",
                "baseline",
            )
        return "describe what the code does today and pin it with passing tests", "baseline"
    if status == "draft":
        return "finish the spec and its interview, then open the spec PR for review", "spec"
    if status == "approved":
        if "test" in has:
            return "the test PR is in progress: prove every criterion red, then get it reviewed", "tests-first"
        return "write the failing tests and open the test PR", "tests-first"
    if status == "tests-locked":
        if implementing:
            return "implementation in progress: get every check green, then self-review and open the PR", "self-review"
        return "implement against the locked tests", "implement"
    return "done; capture lessons at the next retro", None


def steps(root: Path, base: str) -> list[Step]:
    core = load_core(root)
    if core is None:
        return []
    config, lock, spec, status = core
    cfg = config.load_config(root)
    branches = spec_branches(root)
    out = []
    for spec_id, folder in spec.list_specs(root, cfg).items():
        rel = (folder / "status.yml").relative_to(root).as_posix()
        mine = sorted(branches.get(spec_id, []))
        feature = next((b for b in mine if b.startswith("feature/")), None)
        ref = None
        if feature:  # the local branch may be ahead of origin with implementation commits
            ref = feature if git(root, "rev-parse", "--verify", "-q", f"refs/heads/{feature}") else f"origin/{feature}"
        text = (git(root, "show", f"{ref}:{rel}") if ref else None) or git(root, "show", f"{base}:{rel}")
        if text is None:
            text = (folder / "status.yml").read_text(encoding="utf-8")
        try:
            st = status.parse_status(text, cfg)
        except status.SpecStatusError as e:
            out.append(Step(spec_id, "invalid", False, [], f"fix status.yml: {e}", None))
            continue
        implementing = False
        if ref:
            # Locked on the feature branch: implementing once it has commits after the lock. Locked on main (0.1): always.
            locked_at = lock.lock_commit(root, base, spec.Resolution("found", feature, spec_id, folder), cfg, ref)
            implementing = (
                locked_at is None or (git(root, "rev-list", "--count", f"{locked_at}..{ref}") or "0").strip() != "0"
            )
        # getattr: a repo's vendored core older than 0.4 has no baseline specs
        nxt, skill = decide(st.status, mine, implementing, getattr(st, "baseline", False))
        if st.pii and skill:
            nxt += " (pii: yes, so in Copilot only)"
        out.append(Step(spec_id, st.status, st.pii, mine, nxt, skill))
    return out


def render(found: list[Step], current: str | None) -> str:
    if not found:
        return "No specs yet. Start one with /spec."
    out = ["| Spec | Status | Branches | Next | Skill |", "|---|---|---|---|---|"]
    for s in found:
        skill = f"/{s.skill}" if s.skill else ""
        out.append(f"| {s.spec} | {s.status} | {', '.join(s.branches) or '-'} | {s.next} | {skill} |")
    m = re.match(rf"(?:{'|'.join(PREFIXES)})/(\d+)-", current or "")
    here = next((s for s in found if m and s.spec == m[1]), None)
    if here:
        out.append(f"\nOn {current}: {here.next}" + (f" (/{here.skill})." if here.skill else "."))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--base", default="origin/main", help="branch whose status.yml counts (default: origin/main)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if load_core(root) is None:
        print("This repo isn't set up for Lockstep yet. Run /bootstrap-repo first.")
        return 1
    found = steps(root, args.base)
    if args.json:
        print(json.dumps([asdict(s) for s in found], indent=2))
    else:
        current = (git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
        print(render(found, current))
    return 0


if __name__ == "__main__":
    sys.exit(main())
