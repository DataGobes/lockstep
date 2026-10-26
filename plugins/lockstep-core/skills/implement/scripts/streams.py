#!/usr/bin/env python3
"""Run independent slices of a spec in parallel: one git worktree and branch per stream, one agent per worktree.

  python3 streams.py add <stream> [<stream> ...] --root <feature worktree>
  python3 streams.py list --root <feature worktree>
  python3 streams.py remove <stream> --root <feature worktree>

Run from the spec's feature worktree (on feature/<id>-<slug>, as start_implement.py made it). ``add`` creates, for
each stream, a branch feature/<id>-<slug>--<stream> from the feature branch's tip and a worktree next to the feature
worktree, <feature worktree>--<stream>. The stream branch still names the spec, so the hooks and checks protect the
locked tests there as on the feature branch. Each stream comes back through a PR into the feature branch; ``remove``
then deletes its worktree and branch (refusing while the branch has unmerged commits) and prunes. Prints JSON.
Stdlib only. Parallel streams follow SDTRD's worktree protocol.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SEP = "--"
_FEATURE = re.compile(r"^feature/(?P<id>\d+)-[a-z0-9-]+$")
_STREAM = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class StreamError(RuntimeError):
    pass


def git(root: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise StreamError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def feature_branch(root: Path) -> str:
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD", check=False).strip()
    if not _FEATURE.match(branch) or SEP in branch:
        raise StreamError(
            f"run this in the spec's feature worktree, on feature/<id>-<slug>; this is {branch or 'a detached HEAD'}"
        )
    return branch


def worktrees(root: Path) -> dict[str, Path]:
    """Branch -> worktree path, for every worktree of this repo."""
    found, path = {}, None
    for line in git(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/") and path is not None:
            found[line.removeprefix("branch refs/heads/")] = path
    return found


def add(root: Path, streams: list[str]) -> list[dict]:
    feature = feature_branch(root)
    bad = [s for s in streams if not _STREAM.match(s)]
    if bad or len(set(streams)) != len(streams):
        raise StreamError(f"stream names are distinct lower-case words joined by hyphens, got {streams}")
    if git(root, "status", "--porcelain").strip():
        raise StreamError("commit the shared contracts first: streams start from the feature branch's last commit")
    existing = worktrees(root)
    created = []
    for stream in streams:
        branch, path = f"{feature}{SEP}{stream}", root.parent / f"{root.name}{SEP}{stream}"
        if branch in existing or git(root, "branch", "--list", branch).strip():
            raise StreamError(f"{branch} already exists; remove that stream first")
        if path.exists():
            raise StreamError(f"{path} already exists")
        git(root, "worktree", "add", "-q", "-b", branch, str(path), feature)
        created.append({"stream": stream, "branch": branch, "worktree": str(path)})
    return created


def list_streams(root: Path) -> list[dict]:
    feature = feature_branch(root)
    prefix = f"{feature}{SEP}"
    out = []
    for branch in sorted(b for b in git(root, "branch", "--format=%(refname:short)").split() if b.startswith(prefix)):
        ahead = int(git(root, "rev-list", "--count", f"{feature}..{branch}").strip() or 0)
        path = worktrees(root).get(branch)
        out.append(
            {
                "stream": branch.removeprefix(prefix),
                "branch": branch,
                "worktree": str(path) if path else None,
                "unmerged_commits": ahead,
            }
        )
    return out


def remove(root: Path, stream: str) -> dict:
    feature = feature_branch(root)
    branch = f"{feature}{SEP}{stream}"
    if not git(root, "branch", "--list", branch).strip():
        raise StreamError(f"no stream branch {branch}")
    if not _merged(root, feature, branch):
        raise StreamError(
            f"{branch} has changes that are not on {feature} yet; merge its PR into {feature} and pull, "
            "or delete it by hand if the stream is abandoned"
        )
    path = worktrees(root).get(branch)
    if path is not None:
        git(root, "worktree", "remove", str(path))
    git(root, "branch", "-D", branch)
    git(root, "worktree", "prune")
    return {"stream": stream, "branch": branch, "removed": True}


def _merged(root: Path, feature: str, branch: str) -> bool:
    """Whether merging the stream into the feature branch would change nothing (also after a squash merge)."""
    if branch in git(root, "branch", "--format=%(refname:short)", "--merged", feature).split():
        return True
    tree = git(root, "merge-tree", "--write-tree", feature, branch, check=False).split()  # git 2.38+
    return bool(tree) and tree[0] == git(root, "rev-parse", f"{feature}^{{tree}}").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["add", "list", "remove"])
    ap.add_argument("streams", nargs="*", help="stream names, e.g. storage api")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="the spec's feature worktree")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "add":
            if not args.streams:
                ap.error("add needs at least one stream name")
            result: object = add(root, args.streams)
        elif args.command == "list":
            result = list_streams(root)
        else:
            if len(args.streams) != 1:
                ap.error("remove takes one stream name")
            result = remove(root, args.streams[0])
    except StreamError as e:
        print(f"streams: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
