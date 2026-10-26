"""Load and validate a repo's ``lockstep.toml``.

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

CONFIG_FILE = "lockstep.toml"
TRACKS = ("data", "ai")
MODES = ("warn", "enforce")
RULE_TARGETS = ("content", "command")
AC_FORMATS = ("any", "ears", "given-when-then")


class ConfigError(ValueError):
    """lockstep.toml is unreadable or invalid."""


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
    # .lockstep/ is the vendored core: a setup or upgrade PR copies thousands of lines nobody writes by hand.
    ignore: tuple[str, ...] = ("target/**", "**/*.lock", "uv.lock", "**/manifest.json", ".lockstep/**")


@dataclass(frozen=True)
class Lanes:
    # Branch prefixes for work that needs no spec. Chores: dependency bumps, config, tooling.
    chore: tuple[str, ...] = ("chore/",)
    # The bug lane: a bug report and a new regression test, then the fix, in one PR.
    bugfix: tuple[str, ...] = ("bugfix/", "hotfix/")
    bug_reports_dir: str = "specs/bug-reports"
    # Changes that never need a spec: the specs themselves and documentation.
    no_spec_needed: tuple[str, ...] = ("specs/**", "docs/**", "**/*.md")


@dataclass(frozen=True)
class Specs:
    # How acceptance criteria are written: "ears" (WHEN ... THE SYSTEM SHALL ...), "given-when-then" (GIVEN, WHEN and
    # THEN steps under the criterion), or "any" (either, unchecked). check_ac_traceability holds every spec to it.
    ac_format: str = "any"
    # Specs with at least this many active criteria also need research.md and design.md before approval (0: off).
    # Any spec can ask for them alone with `design: yes` in status.yml.
    design_from_criteria: int = 0
    # Keep specs/living/<capability>.md: the criteria in force per capability, generated from the specs.
    living: bool = False
    # Quick lane: a spec with at most this many criteria (and no design step) may skip its own spec PR and arrive in
    # the test PR, reviewed together with its failing tests (0: off, every spec needs a spec PR first).
    quick_max_criteria: int = 0


@dataclass(frozen=True)
class Rule:
    """A team's own rule: a regex that must not appear in added code (``on = "content"``) or in an agent's shell
    command (``on = "command"``). Content rules run in the team_rules hook and in CI; command rules in the hook only."""

    name: str
    pattern: str
    message: str
    on: str = "content"
    paths: tuple[str, ...] = ("**",)  # content rules only

    @property
    def regex(self) -> re.Pattern[str]:
        return re.compile(self.pattern)


@dataclass(frozen=True)
class Enforcement:
    # "enforce" blocks; "warn" lets the change through, says it would have been blocked and logs it,
    # so a pilot can measure how often a gate fires before it starts blocking. Per check, "" means the default.
    # The guard_bash hook (prod deploys, force-pushes) is not listed: it always enforces.
    default: str = "enforce"
    protect_tests: str = ""
    pr_size: str = ""
    jira_key: str = ""
    spec_required: str = ""
    test_tamper: str = ""
    ac_traceability: str = ""
    review_rules: str = ""
    living_specs: str = ""
    team_rules: str = ""

    def mode(self, check: str) -> str:
        """The mode for a hook or check name, with or without its ``check_`` prefix."""
        name = check.removeprefix("check_")
        if name not in self.__dataclass_fields__ or name == "default":
            return "enforce"  # anything not configurable, such as guard_bash
        return getattr(self, name) or self.default


@dataclass(frozen=True)
class Config:
    core_version: str = "0.3"
    specs_dir: str = "specs"
    # Must capture the spec id in a group named "id".
    branch_pattern: str = r"^(?:feature|bugfix|hotfix|test|spec|baseline)/(?P<id>\d{4})-"
    tracks: tuple[str, ...] = TRACKS
    # Jira project keys this repo's work items live in; issue keys look like MXAAI-123.
    jira_projects: tuple[str, ...] = ("MXAAI",)
    jira_multiple_keys: bool = False  # may one PR name more than one issue key?
    jira_required: bool = True  # false for teams without Jira: keys are checked when given, never demanded
    protect: Protect = field(default_factory=Protect)
    pii: Pii = field(default_factory=Pii)
    pr_size: PrSize = field(default_factory=PrSize)
    lanes: Lanes = field(default_factory=Lanes)
    specs: Specs = field(default_factory=Specs)
    enforcement: Enforcement = field(default_factory=Enforcement)
    rules: tuple[Rule, ...] = ()
    source: Path | None = None

    @property
    def branch_regex(self) -> re.Pattern[str]:
        return re.compile(self.branch_pattern)

    @property
    def jira_key_regex(self) -> re.Pattern[str]:
        """Matches one issue key of an allowed project. Use fullmatch() to validate, search() to find."""
        projects = "|".join(re.escape(p) for p in self.jira_projects)
        return re.compile(rf"(?<![A-Za-z0-9])(?:{projects})-[1-9]\d*(?![A-Za-z0-9])")

    def without_source(self) -> Config:
        return replace(self, source=None)


# TOML table -> (section dataclass field on Config, or None for top-level keys).
_SECTIONS: dict[str, str | None] = {
    "lockstep": None,
    "jira": None,
    "protect": "protect",
    "pii": "pii",
    "pr_size": "pr_size",
    "lanes": "lanes",
    "specs": "specs",
    "enforcement": "enforcement",
}
_TOP_LEVEL_KEYS = {
    "lockstep": {
        "core_version": "core_version",
        "specs_dir": "specs_dir",
        "branch_pattern": "branch_pattern",
        "tracks": "tracks",
    },
    "jira": {"projects": "jira_projects", "multiple_keys": "jira_multiple_keys", "required": "jira_required"},
}


def load_config(root: Path) -> Config:
    path = Path(root) / CONFIG_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()  # only a missing file means defaults; a directory or unreadable file is an error
    except OSError as e:
        raise ConfigError(f"{path}: cannot read {CONFIG_FILE}: {e}") from e
    return parse_config(text, path)


def parse_config(text: str, path: Path) -> Config:
    """``lockstep.toml`` text -> Config; ``path`` names it in errors."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: cannot parse {CONFIG_FILE}: {e}") from e

    top: dict[str, Any] = {}
    sections: dict[str, Any] = {}
    defaults = Config()
    for table, values in raw.items():
        if table == "rules":
            top["rules"] = _rules(path, values)
            continue
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


def _rules(path: Path, values: Any) -> tuple[Rule, ...]:
    """``[[rules]]`` tables -> Rule objects, every key checked."""
    if not isinstance(values, list) or not all(isinstance(v, dict) for v in values):
        raise ConfigError(f"{path}: rules must be written as [[rules]] tables")
    known = Rule.__dataclass_fields__
    rules = []
    for n, item in enumerate(values, start=1):
        unknown = [k for k in item if k not in known]
        if unknown:
            raise ConfigError(f"{path}: unknown key rules.{unknown[0]} in rule {n}")
        missing = [k for k in ("name", "pattern", "message") if k not in item]
        if missing:
            raise ConfigError(f"{path}: rule {n} needs {', '.join(missing)}")
        kwargs = {}
        for key, value in item.items():
            default = Rule.paths if key == "paths" else ""
            kwargs[key] = _coerce(path, f"rules.{key}", value, default)
        rule = Rule(**kwargs)
        where = f"rule {rule.name!r}"
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", rule.name):
            raise ConfigError(f"{path}: {where}: name must be lower-case words joined by hyphens")
        if rule.on not in RULE_TARGETS:
            raise ConfigError(f"{path}: {where}: on must be one of {', '.join(RULE_TARGETS)}")
        if rule.on == "command" and "paths" in item:
            raise ConfigError(f"{path}: {where}: paths applies to content rules only")
        try:
            re.compile(rule.pattern)
        except re.error as e:
            raise ConfigError(f"{path}: {where}: pattern is not a valid regex: {e}") from e
        rules.append(rule)
    names = [r.name for r in rules]
    if len(set(names)) != len(names):
        raise ConfigError(f"{path}: rule names must be unique")
    return tuple(rules)


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
    try:
        regex = re.compile(cfg.branch_pattern)
    except re.error as e:
        raise ConfigError(f"{path}: branch_pattern is not a valid regex: {e}") from e
    if "id" not in regex.groupindex:
        raise ConfigError(f"{path}: branch_pattern needs a named group (?P<id>...)")
    bad_projects = [p for p in cfg.jira_projects if not re.fullmatch(r"[A-Z][A-Z0-9_]+", p)]
    if bad_projects or not cfg.jira_projects or len(set(cfg.jira_projects)) != len(cfg.jira_projects):
        raise ConfigError(
            f"{path}: jira.projects must be distinct Jira project keys such as MXAAI, got {list(cfg.jira_projects)}"
        )
    bad = [t for t in cfg.tracks if t not in TRACKS]
    if bad or not cfg.tracks or len(set(cfg.tracks)) != len(cfg.tracks):
        raise ConfigError(
            f"{path}: tracks must be a non-empty subset of {list(TRACKS)} without duplicates, got {list(cfg.tracks)}"
        )
    lanes = cfg.lanes
    if set(lanes.chore) & set(lanes.bugfix) or not all(p.endswith("/") for p in (*lanes.chore, *lanes.bugfix)):
        raise ConfigError(f"{path}: lanes.chore and lanes.bugfix must be distinct branch prefixes ending in '/'")
    if cfg.specs.ac_format not in AC_FORMATS:
        raise ConfigError(f"{path}: specs.ac_format must be one of {', '.join(AC_FORMATS)}")
    if cfg.specs.design_from_criteria < 0:
        raise ConfigError(f"{path}: specs.design_from_criteria must be 0 (off) or more")
    if cfg.specs.quick_max_criteria < 0:
        raise ConfigError(f"{path}: specs.quick_max_criteria must be 0 (off) or more")
    e = cfg.enforcement
    bad_modes = [k for k in e.__dataclass_fields__ if getattr(e, k) not in (MODES if k == "default" else ("", *MODES))]
    if bad_modes:
        raise ConfigError(f"{path}: enforcement.{bad_modes[0]} must be one of {', '.join(MODES)}")
    s = cfg.pr_size
    if not 0 < s.warn_lines <= s.fail_lines:
        raise ConfigError(f"{path}: pr_size needs 0 < warn_lines <= fail_lines")
    if not 0 < s.max_files <= 100:
        raise ConfigError(f"{path}: pr_size.max_files must be 1-100 (Copilot code review limit)")
