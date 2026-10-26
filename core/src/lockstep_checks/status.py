"""Parse a spec's ``status.yml``.

The file is a flat ``key: value`` list that people edit by hand and hooks read on
every tool call, so this parser accepts only that subset of YAML and rejects
everything else instead of guessing. No YAML library is needed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .config import TRACKS, Config

LIFECYCLE = ("draft", "approved", "tests-locked", "implemented")
LOCKED_STATES = ("tests-locked", "implemented")
TRACK_VALUES = ("data", "ai", "mixed")
KEYS = ("status", "pii", "track", "jira", "locked_at_commit", "design")
REQUIRED = ("status", "pii", "track")

_LINE = re.compile(r"^(?P<key>[a-z_]+):(?:\s+(?P<value>.*?))?\s*$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")


class SpecStatusError(ValueError):
    """status.yml is invalid."""


@dataclass(frozen=True)
class SpecStatus:
    status: str
    pii: bool
    track: str
    jira: str | None
    locked_at_commit: str | None
    design: bool = False  # research.md and design.md are needed before approval

    @property
    def tests_locked(self) -> bool:
        return self.status in LOCKED_STATES

    def to_dict(self) -> dict:
        return {**asdict(self), "tests_locked": self.tests_locked}


def parse_status(text: str, cfg: Config) -> SpecStatus:
    values: dict[str, str | None] = {}
    for n, line in enumerate(text.splitlines(), start=1):
        stripped = _strip_comment(line).rstrip()
        if not stripped or (n == 1 and stripped == "---"):
            continue
        m = _LINE.match(stripped)
        if not m:
            raise SpecStatusError(f"line {n}: expected 'key: value', got {line.strip()!r}")
        key, value = m["key"], _unquote(key=m["key"], value=m["value"], line=n)
        if key not in KEYS:
            raise SpecStatusError(f"line {n}: unknown key {key!r} (allowed: {', '.join(KEYS)})")
        if key in values:
            raise SpecStatusError(f"line {n}: {key!r} is set twice")
        values[key] = value

    for key in REQUIRED:
        if not values.get(key):
            raise SpecStatusError(f"{key!r} is required")

    status = values["status"]
    if status not in LIFECYCLE:
        raise SpecStatusError(f"status must be one of {', '.join(LIFECYCLE)}, got {status!r}")
    pii = values["pii"]
    if pii not in ("yes", "no"):
        raise SpecStatusError(f"pii must be 'yes' or 'no', got {pii!r}")
    track = values["track"]
    allowed_tracks = [t for t in TRACK_VALUES if t in cfg.tracks or (t == "mixed" and set(TRACKS) <= set(cfg.tracks))]
    if track not in allowed_tracks:
        raise SpecStatusError(f"track must be one of {', '.join(allowed_tracks)} for this repo, got {track!r}")

    jira = values.get("jira")
    if jira is not None and not cfg.jira_key_regex.fullmatch(jira):
        raise SpecStatusError(
            f"jira {jira!r} is not an issue key of {'/'.join(cfg.jira_projects)} (e.g. {cfg.jira_projects[0]}-123)"
        )
    if status != "draft" and jira is None and cfg.jira_required:
        raise SpecStatusError(f"jira is required once status is {status!r}")

    commit = values.get("locked_at_commit")
    if status in LOCKED_STATES and commit is None:
        raise SpecStatusError(f"locked_at_commit is required once status is {status!r}")
    if commit is not None and not _COMMIT.match(commit):
        raise SpecStatusError(f"locked_at_commit must be a commit SHA, got {commit!r}")

    design = values.get("design") or "no"
    if design not in ("yes", "no"):
        raise SpecStatusError(f"design must be 'yes' or 'no', got {design!r}")

    return SpecStatus(
        status=status, pii=pii == "yes", track=track, jira=jira, locked_at_commit=commit, design=design == "yes"
    )


def _strip_comment(line: str) -> str:
    # A '#' starts a comment only at line start or after whitespace, as in YAML.
    m = re.search(r"(^|\s)#", line)
    return line[: m.start()] if m else line


def _unquote(key: str, value: str | None, line: int) -> str | None:
    if not value:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1] or None
    if value[0] in "[{&*!|>'\"":
        raise SpecStatusError(f"line {line}: {key} has unsupported YAML value {value!r}; use a plain word")
    return value
