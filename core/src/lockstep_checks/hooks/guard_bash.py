"""PreToolUse on shell commands: block what an agent must never run.

Blocks commands that target prod, force-push, rewrite history while on main, or
skip tests with pytest selection flags. Matching is deliberately broad: a false
block costs a retry, a missed one can cost production.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
from pathlib import Path

from ..spec import current_branch
from . import Decision, Event, repo_root, run

SHELL_TOOLS = {"Bash", "PowerShell", "bash", "powershell", "shell"}
PROTECTED_BRANCHES = {"main", "master"}

_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.IGNORECASE), why)
    for p, why in (
        (r"(?:^|\s)(?:-t|--target)(?:\s+|=)['\"]?(?:prod|production)\b", "targets prod; agents may deploy to dev only"),
        (
            r"\b(?:--profile|--environment|-e)(?:\s+|=)['\"]?(?:prod|production)\b",
            "targets prod; agents may deploy to dev only",
        ),
        (r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*(?:\s--force(?:-with-lease)?\b|\s-[a-z]*f\b|\s\+\S)", "force-pushes"),
        (r"\bgit\b[^;&|\n]*\bpush\b[^;&|\n]*\s(?:--delete|-d)\s+\S*\b(?:main|master)\b", "deletes a protected branch"),
        (r"\bpytest\b[^;&|\n]*\s(?:-k|--deselect|--ignore(?:-glob)?)(?:\s|=)", "skips tests with a selection flag"),
        (
            r"\bpython3?\s+-m\s+pytest\b[^;&|\n]*\s(?:-k|--deselect|--ignore(?:-glob)?)(?:\s|=)",
            "skips tests with a selection flag",
        ),
    )
)
_HISTORY = re.compile(
    r"\bgit\b[^;&|\n]*\s(?:rebase|filter-branch|filter-repo|reset\s+--hard|commit\b[^;&|\n]*--amend)\b", re.IGNORECASE
)


def command_of(event: Event) -> str:
    args = event.tool_input
    return str(args.get("command") or args.get("input") or args.get("script") or "")


def hook(event: Event) -> Decision:
    if event.tool_name not in SHELL_TOOLS:
        return Decision.allow()
    cmd = command_of(event)
    for pattern, why in _RULES:
        if pattern.search(cmd):
            return _deny(cmd, why)
    for folder in _history_folders(cmd, event.cwd):
        if current_branch(repo_root(folder)) in PROTECTED_BRANCHES:
            return _deny(cmd, "rewrites history on main; work on a feature branch")
    return Decision.allow()


_SEGMENT = re.compile(r"\|\||&&|[;|&\n]")


def _history_folders(cmd: str, cwd: Path) -> list[Path]:
    """The folder each history-rewriting git command runs in, after any `cd` before it and its own `-C`. A folder that
    can't be resolved (`cd $DIR`, `cd -`) counts as the session's folder."""
    folders, here = [], cwd
    for segment in _SEGMENT.split(cmd):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if len(words) == 2 and words[0].lstrip("(") == "cd":
            here = _folder(here, words[1], cwd)
        elif _HISTORY.search(segment):
            i = words.index("git") if "git" in words else -1
            dash_c = i >= 0 and words[i + 1 : i + 2] == ["-C"] and len(words) > i + 2
            folders.append(_folder(here, words[i + 2], cwd) if dash_c else here)
    return folders


def _folder(here: Path, target: str, fallback: Path) -> Path:
    folder = here / os.path.expanduser(target)
    return folder if folder.is_dir() else fallback


def _deny(cmd: str, why: str) -> Decision:
    short = cmd if len(cmd) <= 200 else cmd[:200] + "..."
    return Decision.deny(
        f"BLOCKED by lockstep: this command {why}: {short!r}. Do not look for another way to run it. "
        "If the task needs it, stop and ask the user, who runs it themselves (prod deploys go through the pipeline)."
    )


def main() -> None:
    sys.exit(run(hook))
