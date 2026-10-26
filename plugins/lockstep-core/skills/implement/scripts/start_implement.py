#!/usr/bin/env python3
"""Check that a spec is ready to implement, then create its worktree and feature branch.

  python3 start_implement.py --root <repo> --spec 0042 [--dry-run]

Ready means: the spec is on its feature branch (it came in one PR with its tests) or on origin/main (a spec PR
merged); its status on origin/feature/<id>-<slug> is tests-locked (the test PR merged into the feature branch, so the
lock is real; red tests never go to main), it is not marked pii: yes, and no worktree has the feature branch checked out (one implementation per spec at a time).
Creates ../<repo>-<id> as a git worktree on feature/<id>-<slug>. Prints JSON. Stdlib only.

Specs locked on main by Lockstep 0.1 (the test PR went to main) have no feature branch yet; the branch is then
created from origin/main.
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


def spec_folder(root: Path, spec_id: str, specs_dir: str) -> str:
    """The spec's folder name: from main once the spec PR merged, else from its feature branch (the default one-PR flow,
    where the spec arrives in the test PR and reaches main only with the implementation)."""
    names = git(root, "ls-tree", "--name-only", f"origin/main:{specs_dir}", check=False).split()
    folders = [n for n in names if n.startswith(f"{spec_id}-")]
    if not folders:
        refs = git(root, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/origin/feature/{spec_id}-*")
        for ref in refs.split():
            folder = ref.removeprefix("origin/feature/")
            if "--" not in folder and has_ref(root, f"{ref}:{specs_dir}/{folder}/status.yml"):
                folders.append(folder)
    if not folders:
        raise NotReady(
            f"spec {spec_id} is not on origin/main or on its feature branch yet; merge its test PR (or its spec PR) "
            "first"
        )
    if len(folders) > 1:
        raise NotReady(f"spec id {spec_id} has more than one folder: {', '.join(folders)}")
    return folders[0]


def read_status(root: Path, ref: str, path: str) -> dict[str, str]:
    values = {}
    for line in git(root, "show", f"{ref}:{path}").splitlines():
        m = re.match(r"^(\w+):\s*([^#]*?)\s*(?:#.*)?$", line)
        if m:
            values[m[1]] = m[2].strip("'\"")
    return values


def has_ref(root: Path, ref: str) -> bool:
    return bool(git(root, "rev-parse", "--verify", "-q", ref, check=False).strip())


def checked_out(root: Path, branch: str) -> bool:
    return f"branch refs/heads/{branch}\n" in git(root, "worktree", "list", "--porcelain") + "\n"


def start(root: Path, spec_id: str, specs_dir: str = "specs", dry_run: bool = False) -> dict:
    git(root, "fetch", "--quiet", "origin", check=False)
    folder = spec_folder(root, spec_id, specs_dir)
    branch = f"feature/{folder}"
    source = f"origin/{branch}" if has_ref(root, f"origin/{branch}") else "origin/main"
    status = read_status(root, source, f"{specs_dir}/{folder}/status.yml")
    if status.get("status") not in ("tests-locked", "implemented"):
        raise NotReady(
            f"spec {spec_id} on {source} is '{status.get('status')}'; "
            f"the test PR must merge into {branch} first (tests-locked)"
        )
    if status.get("status") == "implemented":
        raise NotReady(f"spec {spec_id} is already implemented; a change needs a new spec")
    if status.get("pii") == "yes":
        raise NotReady(f"spec {spec_id} is marked pii: yes; implement it in the company Copilot")
    if checked_out(root, branch):
        raise NotReady(f"spec {spec_id} already has implementation work: {branch} is checked out; continue there")
    worktree = root.parent / f"{root.name}-{spec_id}"
    if worktree.exists():
        raise NotReady(f"{worktree} already exists")
    if not dry_run:
        if has_ref(root, f"refs/heads/{branch}"):
            git(root, "worktree", "add", "--quiet", str(worktree), branch)
        else:
            track = "--track" if source != "origin/main" else "--no-track"
            git(root, "worktree", "add", "--quiet", track, "-b", branch, str(worktree), source)
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
