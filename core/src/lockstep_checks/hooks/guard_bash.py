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
    folders, followed = _history_folders(cmd, event.cwd)
    if folders and not followed:
        return _deny(
            cmd, "rewrites history in a checkout lockstep can't work out; run it as plain git in that checkout"
        )
    for folder in folders:
        if current_branch(repo_root(folder)) in PROTECTED_BRANCHES:
            return _deny(cmd, "rewrites history on main; work on a feature branch")
    return Decision.allow()


_SEPARATOR = re.compile(r"(\|\||&&|[;|&\n])")
# Syntax that makes the segments below differ from what the shell runs: subshells, groups, command substitution,
# comments and heredocs.
_UNFOLLOWED = re.compile(r"[()`{}#]|\$\(|<<")
# Git commands that change what a later command in the same line works on: HEAD, the config, the worktrees.
_MOVES_GIT = {"checkout", "switch", "config", "worktree", "init", "clone"}


def _history_folders(cmd: str, cwd: Path) -> tuple[list[Path], bool]:
    """The folder each history-rewriting git command runs in, and whether all of them could be followed. An
    allowlist, not a denylist: only `cd <folder>` joined by `&&` / `;`, and git commands that don't move HEAD or change
    config, are trusted before a rewrite. Anything else could have moved it, and the caller blocks: from a feature
    branch, the session's own folder says nothing about where the command lands."""
    parts = _SEPARATOR.split(cmd)
    folders, here, followed, trusted = [], cwd, not _UNFOLLOWED.search(cmd), True
    for segment, after in zip(parts[0::2], parts[1::2] + [""]):
        try:
            words = shlex.split(segment)
        except ValueError:
            words, followed = segment.split(), False
        if not words:
            continue
        if _HISTORY.search(segment):
            at, _ = _git_command(words, here)
            followed &= trusted and at is not None
            folders.append(at or here)
        elif words[0] == "cd":
            # Only `cd <folder> && ...` or `cd <folder>; ...` carries over to the next command.
            target = _cd_folder(here, words[1]) if len(words) == 2 and after in ("&&", ";", "\n") else None
            trusted &= target is not None
            here = target or here
        else:
            at, subcommand = _git_command(words, here)
            trusted &= at is not None and subcommand not in _MOVES_GIT
    return folders, followed


def _git_command(words: list[str], here: Path) -> tuple[Path | None, str | None]:
    """For a command that starts with git: the folder it runs in, after its `-C` options applied in order as git does,
    and its subcommand. The folder is None when it doesn't start with git (`bash -c`, `xargs`, `FOO=1 git`) or has
    another option before the subcommand (`-c` can set core.worktree)."""
    if words[:1] != ["git"]:
        return None, None
    i = 1
    while i < len(words) and words[i].startswith("-"):
        if words[i] != "-C" or i + 1 == len(words):
            return None, None
        here = _folder(here, words[i + 1])
        if here is None:
            return None, None
        i += 2
    return here, words[i] if i < len(words) else None


def _folder(here: Path, target: str) -> Path | None:
    """Where `git -C <target>` runs: git changes into it as the OS resolves it. None when it isn't a folder (`$DIR`, a
    typo)."""
    folder = here / os.path.expanduser(target)
    return folder if folder.is_dir() else None


def _cd_folder(here: Path, target: str) -> Path | None:
    """Where `cd <target>` lands. The shell takes `..` before symlinks (`link/..` is the folder holding the link), so
    the path is normalised first. None when the shell could land somewhere this can't see: `~` follows the shell's
    $HOME, and with $CDPATH set a bare name is looked up there first."""
    if target.startswith("~") or (os.environ.get("CDPATH") and not target.startswith(("/", "."))):
        return None
    folder = Path(os.path.normpath(here / target))
    return folder if folder.is_dir() else None


def _deny(cmd: str, why: str) -> Decision:
    short = cmd if len(cmd) <= 200 else cmd[:200] + "..."
    return Decision.deny(
        f"BLOCKED by lockstep: this command {why}: {short!r}. Do not look for another way to run it. "
        "If the task needs it, stop and ask the user, who runs it themselves (prod deploys go through the pipeline)."
    )


def main() -> None:
    sys.exit(run(hook))
