"""Match a team's own rules (``[[rules]]`` in lockstep.toml) against added code or a shell command.

The team_rules hook and the check_team_rules PR check both call this module, so an agent is
stopped by the same rule that CI would fail it on. Rules match line by line with ``re.search``.
"""

from __future__ import annotations

from collections.abc import Iterable

from .config import Config, Rule
from .paths import matches_any


def content_hits(cfg: Config, path: str, lines: Iterable[tuple[int, str]]) -> list[tuple[int, Rule]]:
    """(line number, rule) for each added line of ``path`` that a content rule forbids."""
    rules = [r for r in cfg.rules if r.on == "content" and matches_any(path, r.paths)]
    return [(n, r) for n, text in lines for r in rules if r.regex.search(text)]


def command_hits(cfg: Config, command: str) -> list[Rule]:
    return [r for r in cfg.rules if r.on == "command" and any(r.regex.search(line) for line in command.splitlines())]
