"""Load and validate a repo's ``factory.toml``.

The file is optional: a missing file means the documented defaults. Every key is
validated, and an unknown key is an error, because a typo such as ``warn_line``
must never silently switch a gate back to its default.

TOML rather than YAML because ``tomllib`` is in the standard library, so hooks
work in any Python 3.11+ without installing anything.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

CONFIG_FILE = "factory.toml"
TRACKS = ("data", "ai")


class ConfigError(ValueError):
    """factory.toml is unreadable or invalid."""


@dataclass(frozen=True)
class Protect:
    # Paths that become read-only for agents once a spec is tests-locked.
    globs: tuple[str, ...] = (
        "tests/**",
        "**/*.unit_tests.yml",
        "evals/thresholds.yml",
        "evals/datasets/**",
        "**/__snapshots__/**",
    )


@dataclass(frozen=True)
class Pii:
    # Column or field names the prompt hook treats as personal data.
    columns: tuple[str, ...] = (
        "email",
        "phone",
        "iban",
        "first_name",
        "last_name",
        "full_name",
        "date_of_birth",
        "address",
    )


@dataclass(frozen=True)
class PrSize:
    warn_lines: int = 400
    fail_lines: int = 800
    max_files: int = 100  # Copilot code review's hard limit; never raise it
    ignore: tuple[str, ...] = ("target/**", "**/*.lock", "uv.lock", "**/manifest.json")


@dataclass(frozen=True)
class Config:
    core_version: str = "0.1"
    specs_dir: str = "specs"
    # Must capture the spec id in a group named "id".
    branch_pattern: str = r"^(?:feature|bugfix|hotfix|test|spec)/(?P<id>\d{4})-"
    tracks: tuple[str, ...] = TRACKS
    jira_key_pattern: str = r"[A-Z][A-Z0-9]+-\d+"
    protect: Protect = field(default_factory=Protect)
    pii: Pii = field(default_factory=Pii)
    pr_size: PrSize = field(default_factory=PrSize)
    source: Path | None = None

    @property
    def branch_regex(self) -> re.Pattern[str]:
        return re.compile(self.branch_pattern)

    @property
    def jira_key_regex(self) -> re.Pattern[str]:
        return re.compile(rf"^{self.jira_key_pattern}$")

    def without_source(self) -> Config:
        return replace(self, source=None)


# TOML table -> (section dataclass field on Config, or None for top-level keys).
_SECTIONS: dict[str, str | None] = {
    "factory": None,
    "jira": None,
    "protect": "protect",
    "pii": "pii",
    "pr_size": "pr_size",
}
_TOP_LEVEL_KEYS = {
    "factory": {
        "core_version": "core_version",
        "specs_dir": "specs_dir",
        "branch_pattern": "branch_pattern",
        "tracks": "tracks",
    },
    "jira": {"key_pattern": "jira_key_pattern"},
}


def load_config(root: Path) -> Config:
    path = Path(root) / CONFIG_FILE
    if not path.is_file():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path}: cannot parse {CONFIG_FILE}: {e}") from e

    top: dict[str, Any] = {}
    sections: dict[str, Any] = {}
    defaults = Config()
    for table, values in raw.items():
        if table not in _SECTIONS:
            raise ConfigError(f"{path}: unknown table [{table}]")
        if not isinstance(values, dict):
            raise ConfigError(f"{path}: {table} must be a table")
        attr = _SECTIONS[table]
        if attr is None:
            for key, value in values.items():
                if key not in _TOP_LEVEL_KEYS[table]:
                    raise ConfigError(f"{path}: unknown key {table}.{key}")
                name = _TOP_LEVEL_KEYS[table][key]
                top[name] = _coerce(path, f"{table}.{key}", value, getattr(defaults, name))
        else:
            section_default = getattr(defaults, attr)
            known = section_default.__dataclass_fields__
            kwargs = {}
            for key, value in values.items():
                if key not in known:
                    raise ConfigError(f"{path}: unknown key {table}.{key}")
                kwargs[key] = _coerce(path, f"{table}.{key}", value, getattr(section_default, key))
            sections[attr] = replace(section_default, **kwargs)

    cfg = replace(defaults, **top, **sections, source=path)
    _validate(path, cfg)
    return cfg


def _coerce(path: Path, name: str, value: Any, default: Any) -> Any:
    if isinstance(default, tuple):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{path}: {name} must be a list of strings")
        return tuple(value)
    # bool is a subclass of int; reject it explicitly so `warn_lines = true` fails.
    if type(value) is not type(default):
        raise ConfigError(f"{path}: {name} must be {type(default).__name__}, got {type(value).__name__}")
    return value


def _validate(path: Path, cfg: Config) -> None:
    for name in ("branch_pattern", "jira_key_pattern"):
        try:
            regex = re.compile(getattr(cfg, name))
        except re.error as e:
            raise ConfigError(f"{path}: {name} is not a valid regex: {e}") from e
        if name == "branch_pattern" and "id" not in regex.groupindex:
            raise ConfigError(f"{path}: branch_pattern needs a named group (?P<id>...)")
    bad = [t for t in cfg.tracks if t not in TRACKS]
    if bad or not cfg.tracks:
        raise ConfigError(f"{path}: tracks must be a non-empty subset of {list(TRACKS)}, got {list(cfg.tracks)}")
    s = cfg.pr_size
    if not 0 < s.warn_lines <= s.fail_lines:
        raise ConfigError(f"{path}: pr_size needs 0 < warn_lines <= fail_lines")
    if not 0 < s.max_files <= 100:
        raise ConfigError(f"{path}: pr_size.max_files must be 1-100 (Copilot code review limit)")
