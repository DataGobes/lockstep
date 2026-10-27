"""Agent hooks for Claude Code and GitHub Copilot (CLI and VS Code agent mode).

Each hook reads the agent's event JSON on stdin and answers with an exit code:
0 allows, 2 blocks (the message on stderr goes back to the agent). Copilot treats
any non-zero exit as a block, so every allow path must exit 0, and a hook that
crashes blocks: Lockstep hooks fail closed.

A block becomes a warning when ``[enforcement]`` in lockstep.toml puts the hook in warn
mode. Every block and every warn-mode pass is appended to the local event log (events.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import CONFIG_FILE, ConfigError, load_config
from ..spec import current_branch
from . import events

ALLOW, BLOCK = 0, 2


@dataclass(frozen=True)
class Decision:
    block: bool
    message: str = ""
    warnings: tuple[str, ...] = field(default=())

    @staticmethod
    def allow(*warnings: str) -> Decision:
        return Decision(False, "", tuple(warnings))

    @staticmethod
    def deny(message: str) -> Decision:
        return Decision(True, message)


@dataclass(frozen=True)
class Event:
    """The agent's hook payload, normalised across Claude Code and Copilot field names."""

    raw: dict[str, Any]

    @property
    def tool_name(self) -> str:
        return str(self.raw.get("tool_name") or self.raw.get("toolName") or "")

    @property
    def tool_input(self) -> dict[str, Any]:
        value = self.raw.get("tool_input", self.raw.get("toolArgs", {}))
        if isinstance(value, str):  # Copilot may send the arguments as a JSON string
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {"input": value}
        return value if isinstance(value, dict) else {}

    @property
    def cwd(self) -> Path:
        return Path(self.raw.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


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


def _fixes_config(raw: dict) -> bool:
    """An edit whose only target is lockstep.toml: allowed while the config is broken, so it can be repaired."""
    from .protect_tests import EDIT_TOOLS, target_paths  # here: protect_tests imports this module

    event = Event(raw)
    paths = target_paths(event) if event.tool_name in EDIT_TOOLS else []
    return bool(paths) and all(Path(p).name == CONFIG_FILE for p in paths)


def run(hook: Callable[[Event], Decision], stdin: str | None = None) -> int:
    """Parse the event, run the hook, print its message, return the exit code. Errors block."""
    name = hook.__module__.rsplit(".", 1)[-1]
    raw: dict = {}
    try:
        text = sys.stdin.read() if stdin is None else stdin
        raw = json.loads(text) if text.strip() else {}
        if not isinstance(raw, dict):
            raise TypeError("event is not a JSON object")
        event = Event(raw)
        decision = hook(event)
        mode = "enforce"
        if decision.block:
            root = repo_root(event.cwd)
            mode = load_config(root).enforcement.mode(name)  # a broken config raises, and so blocks
            events.record(
                root, name, "blocked" if mode == "enforce" else "warned", current_branch(root), decision.message
            )
    except ConfigError as e:
        if _fixes_config(raw):
            print(
                f"lockstep: {CONFIG_FILE} is invalid ({e}); allowing this edit to it so it can be fixed",
                file=sys.stderr,
            )
            return ALLOW
        print(
            f"lockstep: {CONFIG_FILE} is invalid, so every Lockstep hook blocks until it is fixed: {e}. "
            f"Fix {CONFIG_FILE} first (an edit to it is allowed), or ask the user to.",
            file=sys.stderr,
        )
        return BLOCK
    except Exception as e:  # fail closed on anything unexpected
        print(f"lockstep: hook error, blocking to be safe: {type(e).__name__}: {e}", file=sys.stderr)
        return BLOCK
    for w in decision.warnings:
        print(f"lockstep: {w}", file=sys.stderr)
    if decision.block and mode == "warn":
        print(f"lockstep WARN MODE, allowed this time and logged: {decision.message}", file=sys.stderr)
        return ALLOW
    if decision.block:
        print(decision.message, file=sys.stderr)
        return BLOCK
    return ALLOW
