#!/usr/bin/env python3
"""Read a seeded repo's workflow history: what was added and why, what is due for review, and how the numbers moved.

  python3 ledger.py report --root <repo>          # current practices, their reasons, and the event history
  python3 ledger.py review --root <repo>          # practices past their review date, with hook blocks since
  python3 ledger.py baseline --root <repo>        # git figures at seeding next to the last 90 days

Reads .workflow/workflow.toml, .workflow/ledger.jsonl and the core hook's local log; changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "core"))
import probe as probe_mod
from compose import ComposeError, layers, load_catalog, read_workflow
from seedcore import LEDGER, hook_log


def events(root: Path) -> list[dict]:
    path = root / LEDGER
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def report(root: Path) -> list[str]:
    w = read_workflow(root)
    out = [f"Seeded {w['seeded_at'][:10]}. Practices on top of the core:"]
    for p in w["practice"]:
        out.append(f"  {p['id']:<22} since {p['added']}  ({p['source']}) {p['reason']}")
    if not w["practice"]:
        out.append("  none")
    out.append("History:")
    for e in events(root):
        out.append(f"  {e['time'][:10]} {e['action']:<8} {e['practice']:<22} {e['reason']}")
    return out


def review(root: Path, today: date) -> list[str]:
    w = read_workflow(root)
    catalog = load_catalog(layers(root, []))
    blocks = Counter(e.get("rule", "?") for e in hook_log(root))
    out = []
    for p in w["practice"]:
        days = int(catalog.get(p["id"], {}).get("review_after_days", 90))
        age = (today - date.fromisoformat(p["added"])).days
        if age >= days:
            out.append(
                f"{p['id']}: added {age} days ago (review after {days}). Has its failure been seen since? "
                "If not, propose removing it."
            )
    out.append(
        f"Core hook blocks recorded on this machine: {sum(blocks.values())}"
        + (f" ({', '.join(f'{k}: {v}' for k, v in blocks.items())})" if blocks else "")
    )
    return out


def baseline(root: Path) -> list[str]:
    seed = next((e for e in events(root) if e["action"] == "seed"), None)
    if not seed:
        return ["No seed event in the ledger."]
    now = probe_mod.history(root)
    then = seed.get("baseline", {})
    out = [f"{'':<14}{'at seeding':>12}{'last 90 days':>14}"]
    for k in ("commits", "contributors", "reverts", "fix_commits", "test_changes"):
        out.append(f"{k:<14}{then.get(k, '-'):>12}{now[k]:>14}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["report", "review", "baseline"])
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--today", type=date.fromisoformat, default=datetime.now(UTC).date())
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        lines = {
            "report": lambda: report(root),
            "review": lambda: review(root, args.today),
            "baseline": lambda: baseline(root),
        }[args.command]()
    except ComposeError as e:
        print(f"ledger: {e}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
