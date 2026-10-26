#!/usr/bin/env python3
"""Check that a spec is ready to implement, then create its worktree and feature branch.

  python3 start_implement.py --root <repo> --spec 0042 [--dry-run]

Ready means: the spec on origin/main has status tests-locked (the test PR is merged, so the lock is real), it is not
marked pii: yes, and no other branch or worktree for this spec exists (one implementation per spec at a time).
Creates ../<repo>-<id> as a git worktree on feature/<id>-<slug>, branched from origin/main. Prints JSON. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class NotReady(RuntimeError):
    pass


def git(root: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise NotReady(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def spec_on_main(root: Path, spec_id: str, specs_dir: str) -> tuple[str, dict[str, str]]:
    names = git(root, "ls-tree", "--name-only", f"origin/main:{specs_dir}", check=False).split()
    folders = [n for n in names if n.startswith(f"{spec_id}-")]
    if not folders:
        raise NotReady(f"spec {spec_id} is not on origin/main yet; merge the spec and test PRs first")
    if len(folders) > 1:
        raise NotReady(f"spec id {spec_id} has more than one folder on main: {', '.join(folders)}")
    text = git(root, "show", f"origin/main:{specs_dir}/{folders[0]}/status.yml")
    values = {}
    for line in text.splitlines():
        m = re.match(r"^(\w+):\s*([^#]*?)\s*(?:#.*)?$", line)
        if m:
            values[m[1]] = m[2].strip("'\"")
    return folders[0], values


def other_work(root: Path, spec_id: str) -> list[str]:
    branches = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes").split()
    pattern = re.compile(rf"(?:^|/)feature/{spec_id}-")
    return [b for b in branches if pattern.search(b)]


def start(root: Path, spec_id: str, specs_dir: str = "specs", dry_run: bool = False) -> dict:
    git(root, "fetch", "--quiet", "origin", check=False)
    folder, status = spec_on_main(root, spec_id, specs_dir)
    if status.get("status") not in ("tests-locked", "implemented"):
        raise NotReady(
            f"spec {spec_id} on main is '{status.get('status')}'; the test PR must merge first (tests-locked)"
        )
    if status.get("status") == "implemented":
        raise NotReady(f"spec {spec_id} is already implemented; a change needs a new spec")
    if status.get("pii") == "yes":
        raise NotReady(f"spec {spec_id} is marked pii: yes; implement it in the company Copilot")
    taken = other_work(root, spec_id)
    if taken:
        raise NotReady(f"spec {spec_id} already has implementation work: {', '.join(taken)}; continue there")
    slug = folder.split("-", 1)[1]
    branch = f"feature/{spec_id}-{slug}"
    worktree = root.parent / f"{root.name}-{spec_id}"
    if worktree.exists():
        raise NotReady(f"{worktree} already exists")
    if not dry_run:
        git(root, "worktree", "add", "--quiet", "-b", branch, str(worktree), "origin/main")
    return {"spec": spec_id, "spec_dir": f"{specs_dir}/{folder}", "branch": branch, "worktree": str(worktree)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--spec", required=True, help="spec id, e.g. 0042")
    ap.add_argument("--specs-dir", default="specs")
    ap.add_argument("--dry-run", action="store_true", help="check only, create nothing")
    args = ap.parse_args(argv)
    try:
        result = start(args.root.resolve(), args.spec, args.specs_dir, args.dry_run)
    except NotReady as e:
        print(f"start_implement: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
