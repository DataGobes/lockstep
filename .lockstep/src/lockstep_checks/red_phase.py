"""Which test files may fail in a PR's quality job: the spec's own tests, while its feature branch is in progress.

Red tests never reach main. The test PR merges failing tests into ``feature/<id>-<slug>``, and stream PRs merge
partial work into it, so a PR into a feature branch carries tests that are red on purpose. Those are the test
files the feature branch adds compared with main. Every other test must still pass. The PR from the feature branch
into main runs the full gate, with nothing excused.

  python -m lockstep_checks.red_phase [--target <PR target branch>] [--main origin/main]

Prints one file per line, nothing when the target is not a feature branch. The target defaults to Azure Pipelines'
``SYSTEM_PULLREQUEST_TARGETBRANCH``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .gitdiff import GitError, changed_files

FEATURE = "feature/"


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def expected_red(root: Path, target: str | None, main: str = "origin/main") -> list[str]:
    target = (target or "").removeprefix("refs/heads/")
    if not target.startswith(FEATURE):
        return []
    return sorted(f.path for f in changed_files(root, main) if f.status == "A" and is_test_file(f.path))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lockstep_checks.red_phase", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--target", default=os.environ.get("SYSTEM_PULLREQUEST_TARGETBRANCH", ""))
    ap.add_argument("--main", default="origin/main", help="the branch red tests must never reach")
    args = ap.parse_args(argv)
    try:
        files = expected_red(args.root.resolve(), args.target, args.main)
    except GitError as e:
        print(f"lockstep_checks: {e}", file=sys.stderr)
        return 1
    print("\n".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
