"""A local log of every hook block and warn-mode pass, to count how often the gates fire.

Each line of ``.git/lockstep/hook-events.jsonl`` is one event. The file sits inside
``.git`` so it is never committed and needs no ``.gitignore`` entry. CI counts the same
gates team-wide with build tags; this log adds what only the agent's hooks see.

  PYTHONPATH=.lockstep/src python3 -m lockstep_checks.hooks.events   # counts per hook
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

LOG = Path("lockstep") / "hook-events.jsonl"


def log_path(root: Path) -> Path | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or not p.stdout.strip():
        return None
    return (Path(root) / p.stdout.strip()) / LOG  # an absolute git dir replaces root


def record(root: Path, hook: str, action: str, branch: str | None, message: str) -> None:
    """Append one event. Never raises: a full disk must not change what the hook decided."""
    path = log_path(root)
    if path is None:
        return
    event = {
        "time": datetime.now(UTC).isoformat(timespec="seconds"),
        "hook": hook,
        "action": action,
        "branch": branch,
        "message": message[:300],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


def summary(path: Path) -> list[str]:
    counts: Counter[tuple[str, str]] = Counter()
    times = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            counts[(e["hook"], e["action"])] += 1
            times.append(e["time"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    if not counts:
        return ["no hook events yet"]
    lines = [f"hook events {min(times)[:10]} to {max(times)[:10]}:"]
    lines += [f"  {hook:<14} {action:<8} {n}" for (hook, action), n in sorted(counts.items())]
    return lines


def main() -> None:
    path = log_path(Path.cwd())
    if path is None or not path.is_file():
        print("no hook events yet")
        sys.exit(0)
    print("\n".join(summary(path)))


if __name__ == "__main__":
    main()
