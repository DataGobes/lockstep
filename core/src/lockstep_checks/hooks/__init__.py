"""Agent hooks for Claude Code and GitHub Copilot (CLI and VS Code agent mode).

Each hook reads the agent's event JSON on stdin and answers with an exit code:
0 allows, 2 blocks (the message on stderr goes back to the agent). Copilot treats
any non-zero exit as a block, so every allow path must exit 0, and a hook that
crashes blocks: Lockstep hooks fail closed.
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
    def prompt(self) -> str:
        return str(self.raw.get("prompt") or "")

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


def run(hook: Callable[[Event], Decision], stdin: str | None = None) -> int:
    """Parse the event, run the hook, print its message, return the exit code. Errors block."""
    try:
        text = sys.stdin.read() if stdin is None else stdin
        raw = json.loads(text) if text.strip() else {}
        if not isinstance(raw, dict):
            raise TypeError("event is not a JSON object")
        decision = hook(Event(raw))
    except Exception as e:  # fail closed on anything unexpected
        print(f"lockstep: hook error, blocking to be safe: {type(e).__name__}: {e}", file=sys.stderr)
        return BLOCK
    for w in decision.warnings:
        print(f"lockstep: {w}", file=sys.stderr)
    if decision.block:
        print(decision.message, file=sys.stderr)
        return BLOCK
    return ALLOW
