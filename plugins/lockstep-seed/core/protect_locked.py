#!/usr/bin/env python3
"""Core hook (PreToolUse) for Claude Code and GitHub Copilot: agents never edit locked tests.

Reads the agent's event JSON on stdin. Exit 0 allows; exit 2 blocks, with the reason on stderr for the agent.
A file is locked when it matches a `path` in .workflow/locks.toml. The workflow's own records (locks, ledger,
core) are locked too, so an agent can't unlock a test by editing the lock file. Fails closed on any error.
CI (check_core.py) is the backstop for anything a hook can't see.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seedcore import SELF_PROTECTED, locks, matches, record_block, repo_root

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "edit", "create", "write", "apply_patch"}
SHELL_TOOLS = {"Bash", "PowerShell", "bash", "shell", "powershell"}
WRITES = {"rm", "mv", "cp", "tee", "truncate", "unlink", "sed", "perl", "Set-Content", "Out-File", "Remove-Item"}
GIT_WRITES = {"rm", "mv", "checkout", "restore", "apply"}
REDIRECT = re.compile(r"\d?>>?\s*([^\s;&|<>]+)")
PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+?)\s*$", re.MULTILINE)


def tool_input(raw: dict) -> dict:
    value = raw.get("tool_input", raw.get("toolArgs", {}))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"input": value}
    return value if isinstance(value, dict) else {}


def edited_paths(args: dict) -> list[str]:
    paths = [str(args[k]) for k in ("file_path", "notebook_path", "path", "filePath") if args.get(k)]
    for key in ("patch", "input"):
        if isinstance(args.get(key), str):
            paths += PATCH_FILE.findall(args[key])
    return paths


def shell_writes(command: str) -> list[str]:
    """Files a shell command would write: redirect targets, and arguments of commands that write what they name."""
    found = REDIRECT.findall(command)
    for segment in re.split(r"\|\||&&|[;|&\n]", command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        if not words:
            continue
        verb = Path(words[0]).name
        if verb in WRITES or (verb == "git" and len(words) > 1 and words[1] in GIT_WRITES):
            found += [w for w in words[1:] if not w.startswith("-")]
    return found


def relative(root: Path, cwd: Path, p: str) -> str | None:
    path = Path(p)
    path = path if path.is_absolute() else cwd / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None  # outside the repo


def decide(raw: dict) -> str | None:
    """The reason to block, or None to allow."""
    name = str(raw.get("tool_name") or raw.get("toolName") or "")
    args = tool_input(raw)
    if name in EDIT_TOOLS:
        targets = edited_paths(args)
    elif name in SHELL_TOOLS:
        targets = shell_writes(str(args.get("command") or args.get("input") or ""))
    else:
        return None
    cwd = Path(raw.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    root = repo_root(cwd)
    locked = {x["path"]: x.get("spec", "") for x in locks(root)}
    for t in targets:
        rel = relative(root, cwd, t)
        if rel is None:
            continue
        if matches(rel, SELF_PROTECTED):
            record_block(root, "core-ledger", rel)
            return f"seed core: {rel} records the team's workflow; only a person changes it, in a PR."
        for glob, spec in locked.items():
            if matches(rel, [glob]):
                why = f" (tests for {spec})" if spec else ""
                record_block(root, "core-locked-tests", rel)
                return (
                    f"seed core: {rel} is a locked test{why}. Don't edit it to make code pass. If the test is wrong, "
                    "stop and tell the user; a person changes it in a PR marked [test-change]."
                )
    return None


def main() -> int:
    try:
        text = sys.stdin.read()
        raw = json.loads(text) if text.strip() else {}
        if not isinstance(raw, dict):
            raise TypeError("event is not a JSON object")
        reason = decide(raw)
    except Exception as e:  # noqa: BLE001 - fail closed: a crashing hook blocks
        print(f"seed core: hook error, blocking to be safe: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
