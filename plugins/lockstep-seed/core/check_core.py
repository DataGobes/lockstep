#!/usr/bin/env python3
"""Core CI check: the three rules every seeded repo shares.

  python3 .workflow/core/check_core.py --base origin/main [--title "<PR title>"]

1. core-ac-tests: every criterion of a spec named in .workflow/locks.toml has a test that names it.
2. core-locked-tests: no locked test, and no lock entry, changes unless the PR is marked [test-change]
   (in the title or a commit subject).
3. core-ledger: .workflow/ledger.jsonl is only appended to, and each line is a valid event.
Exit 0 passes, 1 fails. Prints one line per finding.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedcore import LEDGER, LOCKS, core_config, locks, matches, repo_root

EVENT_KEYS = {"time", "action", "practice", "reason"}
ACTIONS = {"seed", "add", "remove", "keep", "decline"}


def git(root: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def spec_id(spec_path: str) -> str:
    """The id a test uses for a spec: the leading number of its file or folder (specs/0042-x/spec.md -> 0042)."""
    for part in reversed(Path(spec_path).parts):
        m = re.match(r"(\d+)", part)
        if m:
            return m.group(1)
    return Path(spec_path).stem


def check_ac_tests(root: Path, cfg: dict) -> list[str]:
    errors = []
    tests = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    tests = [p for p in tests if matches(p.relative_to(root).as_posix(), cfg["test_globs"])]
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in tests)
    for spec in sorted({x["spec"] for x in locks(root) if x.get("spec")}):
        path = root / spec
        if not path.is_file():
            errors.append(f"core-ac-tests: {spec} is named in {LOCKS} but does not exist")
            continue
        ids = list(dict.fromkeys(re.findall(cfg["ac_pattern"], path.read_text(encoding="utf-8"))))
        if not ids:
            errors.append(f"core-ac-tests: {spec} has no criteria matching {cfg['ac_pattern']}")
        for ac in ids:
            ref = ac if cfg["ac_scope"] == "global" else f"{spec_id(spec)}/{ac}"
            if ref not in corpus:
                errors.append(f"core-ac-tests: {spec} {ac} has no test that names `{ref}`")
    return errors


def check_locked_tests(root: Path, base: str, title: str) -> list[str]:
    code, out = git(root, "diff", "--name-only", f"{base}...HEAD")
    if code != 0:
        return [f"core-locked-tests: cannot diff against {base}; fetch it first (git fetch origin)"]
    _, subjects = git(root, "log", "--format=%s", f"{base}..HEAD")
    if "[test-change]" in title or "[test-change]" in subjects:
        return []
    _, old = git(root, "show", f"{base}:{LOCKS.as_posix()}")
    try:
        old_locks = tomllib.loads(old).get("lock", []) if old else []
    except tomllib.TOMLDecodeError:
        old_locks = []
    globs = [x["path"] for x in old_locks if isinstance(x, dict) and x.get("path")]
    errors = [
        f"core-locked-tests: {f} is a locked test and changed; a person marks the PR [test-change] if that's intended"
        for f in out.split()
        if matches(f, globs)
    ]
    now = {x["path"] for x in locks(root)}
    errors += [f"core-locked-tests: the lock on {g} was removed without [test-change]" for g in globs if g not in now]
    return errors


def check_ledger(root: Path, base: str) -> list[str]:
    path = root / LEDGER
    if not path.is_file():
        return [f"core-ledger: {LEDGER} is missing"]
    text = path.read_text(encoding="utf-8")
    errors = []
    code, old = git(root, "show", f"{base}:{LEDGER.as_posix()}")
    if code == 0 and not text.startswith(old):
        errors.append(f"core-ledger: {LEDGER} was rewritten; it may only be appended to")
    for n, line in enumerate(text.splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"core-ledger: line {n} is not JSON")
            continue
        missing = EVENT_KEYS - set(event)
        if missing:
            errors.append(f"core-ledger: line {n} lacks {', '.join(sorted(missing))}")
        elif event["action"] not in ACTIONS:
            errors.append(f"core-ledger: line {n} has unknown action {event['action']!r}")
        elif event["action"] in {"add", "remove"} and not str(event["reason"]).strip():
            errors.append(f"core-ledger: line {n} ({event['action']} {event['practice']}) gives no reason")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check the seeded workflow's fixed core.")
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--title", default=os.environ.get("PR_TITLE", ""))
    args = ap.parse_args(argv)
    root = repo_root(args.root)
    cfg = core_config(root)
    errors = check_ac_tests(root, cfg) + check_locked_tests(root, args.base, args.title) + check_ledger(root, args.base)
    for e in errors:
        print(e)
    print(f"seed core: {'FAIL' if errors else 'ok'} ({len(errors)} finding{'s' if len(errors) != 1 else ''})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
