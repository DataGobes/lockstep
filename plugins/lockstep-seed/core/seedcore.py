"""Shared helpers for the fixed core: config, locks and path matching. Standard library only.

Copied into a repo's `.workflow/core/` by compose.py, next to protect_locked.py and check_core.py.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

WORKFLOW = Path(".workflow")
CONFIG = WORKFLOW / "workflow.toml"
LOCKS = WORKFLOW / "locks.toml"
LEDGER = WORKFLOW / "ledger.jsonl"
# Files that define the workflow itself: an agent may not edit them with its file tools.
SELF_PROTECTED = (LOCKS.as_posix(), LEDGER.as_posix(), (WORKFLOW / "core").as_posix() + "/*")
DEFAULT_CORE = {
    "ac_pattern": r"AC-\d{3}",
    "ac_scope": "spec",  # "spec": tests name <spec id>/AC-001; "global": ids are unique, tests name AC-001
    "spec_globs": ["specs/*.md", "specs/*/spec.md"],
    "test_globs": ["tests/**", "**/test_*.py", "**/*_test.py", "**/*.test.ts", "**/*.spec.ts", "**/tests/**"],
}


def repo_root(start: Path) -> Path:
    try:
        p = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return start
    return Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else start


def load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def core_config(root: Path) -> dict:
    return DEFAULT_CORE | load_toml(root / CONFIG).get("core", {})


def locks(root: Path) -> list[dict]:
    """Each lock: {path: glob, spec: path of the spec whose tests these are}."""
    return [x for x in load_toml(root / LOCKS).get("lock", []) if isinstance(x, dict) and x.get("path")]


def matches(rel: str, globs) -> bool:
    rel = rel.removeprefix("./")
    for g in globs:
        if fnmatch.fnmatchcase(rel, g) or (g.startswith("**/") and fnmatch.fnmatchcase(rel, g[3:])):
            return True
    return False


def _git_dir(root: Path) -> Path | None:
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
    return (Path(root) / p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else None


def record_block(root: Path, rule: str, target: str) -> None:
    """Append a hook block to .git/seed/hook-events.jsonl (never committed). Never raises."""
    git_dir = _git_dir(root)
    if git_dir is None:
        return
    try:
        path = git_dir / "seed" / "hook-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            event = {"time": datetime.now(UTC).isoformat(timespec="seconds"), "rule": rule, "target": target}
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


def hook_log(root: Path) -> list[dict]:
    git_dir = _git_dir(root)
    path = git_dir / "seed" / "hook-events.jsonl" if git_dir else None
    if not path or not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
