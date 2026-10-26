#!/usr/bin/env python3
"""Collect the evidence for a Lockstep retro from git history.

  python3 retro.py --root <repo> --since 2026-10-01 [--until 2026-10-31] [--ref origin/main] [--json]

Reads the first-parent history of the main branch (one entry per merged PR when PRs are squash-merged) and sorts
the commits it finds into reverts, `[test-change]` PRs and fixes. Hooks keep no log, so blocked agent actions come
from the people in the retro, not from this script. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_REVERT = re.compile(r"^revert\b", re.IGNORECASE)
_TEST_CHANGE = re.compile(r"\[test-change\]", re.IGNORECASE)
_FIX = re.compile(r"\b(?:fix|fixes|fixed|hotfix|bugfix)\b", re.IGNORECASE)
_SPEC = re.compile(r"\bspec[ /-]?(\d{4})\b", re.IGNORECASE)


@dataclass
class Entry:
    sha: str
    date: str
    subject: str
    kind: str  # revert | test-change | fix
    spec: str | None


def classify(subject: str) -> str | None:
    if _REVERT.search(subject):
        return "revert"
    if _TEST_CHANGE.search(subject):
        return "test-change"
    if _FIX.search(subject):
        return "fix"
    return None


def history(root: Path, ref: str, since: str, until: str | None) -> list[tuple[str, str, str]]:
    cmd = [
        "git",
        "-C",
        str(root),
        "log",
        "--first-parent",
        "--date=short",
        "--format=%h%x1f%ad%x1f%s",
        f"--since={since}",
    ]
    if until:
        cmd.append(f"--until={until} 23:59:59")
    cmd.append(ref)
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [tuple(line.split("\x1f", 2)) for line in out.splitlines() if line]


def collect(commits: list[tuple[str, str, str]]) -> tuple[list[Entry], int]:
    found = []
    for sha, date, subject in commits:
        kind = classify(subject)
        if kind:
            m = _SPEC.search(subject)
            found.append(Entry(sha, date, subject, kind, m.group(1) if m else None))
    return found, len(commits)


def render(entries: list[Entry], total: int) -> str:
    out = [f"{total} commit(s) on main in the range"]
    for kind in ("revert", "test-change", "fix"):
        rows = [e for e in entries if e.kind == kind]
        out.append(f"\n{kind}: {len(rows)}")
        out.extend(f"  {e.date} {e.sha} {e.subject}" for e in rows)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--since", required=True, help="first day, YYYY-MM-DD")
    ap.add_argument("--until", help="last day, YYYY-MM-DD (default: today)")
    ap.add_argument("--ref", default="origin/main", help="branch to read (default: origin/main)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    for day in filter(None, (args.since, args.until)):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            ap.error(f"dates are YYYY-MM-DD, not {day!r}")
    try:
        entries, total = collect(history(args.root, args.ref, args.since, args.until))
    except subprocess.CalledProcessError as e:
        print(f"retro: git log failed: {e.stderr.strip()}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"commits": total, "entries": [asdict(e) for e in entries]}, indent=2))
    else:
        print(render(entries, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
