#!/usr/bin/env python3
"""Rank the areas of an existing codebase by how often they change, to choose what to pin first.

  python3 hotspots.py --root <repo> [--since "12 months ago"] [--depth 2] [--top 15] [--ref origin/main] [--json]

Counts, per folder at --depth (a file at the top level counts as itself), the commits on --ref since --since that
changed its code, the files changed and the authors. Tests, specs, docs, Markdown, lock files and .lockstep/ don't
count as code. An area is "pinned" when some spec.md under specs/ names its path, usually in a baseline spec's scope.
Areas that change often and aren't pinned are where a baseline pays off first. Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

NOT_CODE = (
    "tests/*",
    "*/tests/*",
    "test_*.py",
    "*/test_*.py",
    "*_test.py",
    "*.unit_tests.yml",
    "specs/*",
    "docs/*",
    "*.md",
    ".lockstep/*",
    "*.lock",
    "uv.lock",
    ".github/*",
    ".azuredevops/*",
)


@dataclass
class Area:
    path: str
    commits: int = 0
    files: int = 0
    authors: int = 0
    pinned: bool = False
    _shas: set[str] = field(default_factory=set, repr=False)
    _files: set[str] = field(default_factory=set, repr=False)
    _authors: set[str] = field(default_factory=set, repr=False)


def is_code(path: str) -> bool:
    return not any(fnmatch.fnmatchcase(path, pattern) for pattern in NOT_CODE)


def area_of(path: str, depth: int) -> str:
    parts = path.split("/")
    return "/".join(parts[: min(depth, len(parts) - 1)]) or path


def changes(root: Path, ref: str, since: str) -> list[tuple[str, str, str]]:
    """(commit, author email, path) for every code file each commit on ``ref`` changed since ``since``."""
    out = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "log",
            "--no-merges",
            f"--since={since}",
            "--format=%x1e%H%x1f%ae",
            "--name-only",
            ref,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows = []
    for block in out.split("\x1e")[1:]:
        head, _, names = block.partition("\n")
        sha, _, author = head.partition("\x1f")
        rows += [(sha, author, name) for name in names.split("\n") if name.strip() and is_code(name.strip())]
    return rows


def spec_text(root: Path, specs_dir: str) -> str:
    folder = root / specs_dir
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(folder.glob("*/spec.md"))
        if not p.parent.name.startswith("_")
    )


def rank(rows: list[tuple[str, str, str]], depth: int, specs: str, top: int) -> list[Area]:
    areas: dict[str, Area] = {}
    for sha, author, path in rows:
        area = areas.setdefault(area_of(path, depth), Area(area_of(path, depth)))
        area._shas.add(sha)
        area._files.add(path)
        area._authors.add(author)
    for area in areas.values():
        area.commits, area.files, area.authors = len(area._shas), len(area._files), len(area._authors)
        # the path as a whole word: src/pricing is not pinned by a spec that names src/pricing_v2
        area.pinned = re.search(rf"(?<![\w./-]){re.escape(area.path)}(?![\w.-])", specs) is not None
    return sorted(areas.values(), key=lambda a: (-a.commits, -a.files, a.path))[:top]


def render(found: list[Area], since: str) -> str:
    if not found:
        return f"No code changes since {since}."
    out = ["| Area | Commits | Files | Authors | Pinned |", "|---|---|---|---|---|"]
    out += [f"| {a.path} | {a.commits} | {a.files} | {a.authors} | {'yes' if a.pinned else 'no'} |" for a in found]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--since", default="12 months ago", help="git date, e.g. 2026-01-01 or '6 months ago'")
    ap.add_argument("--depth", type=int, default=2, help="folder depth that makes an area (default 2)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--ref", default="origin/main", help="branch whose history counts (default: origin/main)")
    ap.add_argument("--specs-dir", default="specs")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.depth < 1 or args.top < 1:
        ap.error("--depth and --top take 1 or more")
    root = args.root.resolve()
    try:
        rows = changes(root, args.ref, args.since)
    except subprocess.CalledProcessError as e:
        print(f"hotspots: git log failed: {e.stderr.strip()} (is {args.ref} fetched?)", file=sys.stderr)
        return 1
    found = rank(rows, args.depth, spec_text(root, args.specs_dir), args.top)
    if args.json:
        print(json.dumps([{k: v for k, v in asdict(a).items() if not k.startswith("_")} for a in found], indent=2))
    else:
        print(render(found, args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
