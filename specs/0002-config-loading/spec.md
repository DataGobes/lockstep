---
id: 0002
title: lockstep.toml configuration loading as it works today
owner: Gijs Jansen
reviewer: <engineer>
---

# lockstep.toml configuration loading as it works today

A baseline spec describes behaviour the code already has, and pins it with tests that pass today. It changes no
code. Later change specs supersede its criteria like any other spec's. See docs/baseline-specs.md.

## 1. Problem and outcome
`core/src/lockstep_checks/config.py` turns a repo's `lockstep.toml` into the `Config` every hook and CI check reads.
It is the most-changed module in the core (24 commits in the last year) and every gate depends on it: a config that
loads wrongly can silently switch a gate off or on. This baseline pins what loading, defaulting and validation do
today, so later changes to the config schema build on known behaviour. Callers: `cli.py`, `spec.py`, `spec_pr.py`,
the `protect_tests` and `team_rules` hooks, and the hook runner in `hooks/__init__.py`.

## 2. Scope / non-goals
- In scope: `core/src/lockstep_checks/config.py` (`load_config`, `parse_config`, `Enforcement.mode`, the `[[rules]]`
  parser and `_validate`), tested through `load_config(root)` on a temporary directory.
- Out of scope: what each consumer does with the config (the checks and hooks themselves); the `branch_regex` and
  `jira_key_regex` helpers, which keep their existing untagged tests; `templates/lockstep.toml` staying in step with
  the defaults, which `test_template_loads_and_matches_defaults` already guards.
- Not a goal: changing anything. A behaviour that looks wrong is a bug report or an open question, not a criterion.

## 3. Acceptance criteria (each testable)

- AC-001 WHEN the repo root has no `lockstep.toml` THE SYSTEM SHALL return the documented defaults (`specs_dir`
  "specs", `pr_size` 400/800/100, `"tests/**"` among the protected globs) with `source` set to None.
  - Observed in: `core/src/lockstep_checks/config.py:198`
- AC-002 WHEN `lockstep.toml` sets only `[pr_size] warn_lines = 300` THE SYSTEM SHALL return `warn_lines` 300, the
  default for every other key (`fail_lines` stays 800), and the file's path as `source`.
  - Observed in: `core/src/lockstep_checks/config.py:229`, `core/src/lockstep_checks/config.py:240`
- AC-003 WHEN `lockstep.toml` contains a table or key the schema does not know (for example `[nonsense]` or
  `[pr_size] warn_line`) THE SYSTEM SHALL raise `ConfigError` naming that table or key, so a typo never silently
  restores a default.
  - Observed in: `core/src/lockstep_checks/config.py:220`, `core/src/lockstep_checks/config.py:227`,
    `core/src/lockstep_checks/config.py:236`
- AC-004 WHEN a value has a different type from its default, including a bool where an int is expected
  (`warn_lines = true`) or a string where a list of strings is expected (`globs = "tests/**"`) THE SYSTEM SHALL raise
  `ConfigError` saying which type the key must be.
  - Observed in: `core/src/lockstep_checks/config.py:282`, `core/src/lockstep_checks/config.py:287`
- AC-005 WHEN values are the right type but inconsistent THE SYSTEM SHALL raise `ConfigError`: `branch_pattern`
  that is not a regex or has no `(?P<id>...)` group; `tracks` empty, with duplicates or outside `data`/`ai`;
  `pr_size` with `warn_lines` 0 or above `fail_lines`, or `max_files` outside 1-100; `lanes.chore`,
  `lanes.bugfix` and `lanes.feature` sharing a prefix or a prefix not ending in `/`; `specs.ac_format` outside `any`/`ears`/
  `given-when-then`; `specs.design_from_criteria` or `specs.spec_pr_above_criteria` below 0; `specs.spec_pr_for`
  with duplicates or values outside `design`/`contract`/`pii`; an enforcement mode outside `warn`/`enforce`.
  - Observed in: `core/src/lockstep_checks/config.py:292`
- AC-006 WHEN `Enforcement.mode` is asked for a configurable check, named with or without the `check_` prefix, THE
  SYSTEM SHALL return that check's own entry when set, else the table's `default`, else "enforce": with no
  `[enforcement]` table every check is "enforce"; with `default = "warn"` and `test_tamper = "enforce"`,
  `check_test_tamper` is "enforce" and `check_pr_size` and `protect_tests` are "warn".
  - Observed in: `core/src/lockstep_checks/config.py:119`, `core/src/lockstep_checks/config.py:130`
- AC-007 WHEN `Enforcement.mode` is asked for `guard_bash`, `default`, or any name that is not a configurable check
  THE SYSTEM SHALL return "enforce" whatever the table says (and `[enforcement] guard_bash = "warn"` is an unknown
  key, rejected under AC-003).
  - Observed in: `core/src/lockstep_checks/config.py:133`
- AC-008 WHEN `[[rules]]` tables are given THE SYSTEM SHALL load each with `on = "content"` and `paths = ["**"]`
  unless set, rejecting with a `ConfigError` that names the rule any rule that lacks `name`, `pattern` or
  `message`, has a name that is not lower-case words joined by hyphens, an `on` outside `content`/`command`, `paths`
  on a command rule, a pattern that is not a valid regex, an unknown key, or a name another rule already uses, and
  rejecting a plain `[rules]` table with "must be written as [[rules]] tables".
  - Observed in: `core/src/lockstep_checks/config.py:245`
- AC-009 WHEN `[jira] required = false` THE SYSTEM SHALL still require `jira.projects` to be a non-empty list of
  distinct keys matching `[A-Z][A-Z0-9_]+`, keeping the default `["MXAAI"]` when the key is not set, so a key is
  validated whenever one is given.
  - Observed in: `core/src/lockstep_checks/config.py:299`
- AC-010 WHEN `lockstep.toml` exists but is unreadable (for example it is a directory) or is not valid TOML THE
  SYSTEM SHALL raise `ConfigError` with the path and "cannot read" or "cannot parse" respectively; only a missing
  file means defaults.
  - Observed in: `core/src/lockstep_checks/config.py:196`, `core/src/lockstep_checks/config.py:207`

Never delete or renumber a criterion. When a change spec alters this behaviour, it strikes the criterion here and
points to its replacement: `- ~~AC-002~~ superseded by 0057/AC-001`.

## 4. Interfaces and data contract
- Input: `lockstep.toml` at the repo root, read with `tomllib`; `load_config(root: Path) -> Config`,
  `parse_config(text: str, path: Path) -> Config`.
- Output: the frozen dataclasses `Config`, `Protect`, `Pii`, `PrSize`, `Lanes`, `Specs`, `Enforcement`, `Rule`; every
  list in the file becomes a tuple. `Enforcement.mode(name) -> "warn" | "enforce"`.
- Errors: `ConfigError` (a `ValueError`), whose message starts with the file path.
- Consumers: every `check_*` module through `cli.py`, `spec.py` and `spec_pr.py`; the hooks `protect_tests`,
  `team_rules` and the runner in `hooks/__init__.py`, which reads `enforcement.mode` for each hook.

## 5. Test and eval plan
Characterisation tests: they pass on today's code. Name criteria with this spec's id, as in any spec:
`@pytest.mark.ac("0002/AC-001")`, dbt unit test `ac_0002_001_<what>`, `meta: {ac: 0002/AC-001}`, or an `ac` field
`0002/AC-001` in an eval row. An existing test can be adopted by adding only the tag.

| AC | Test (new or adopted) | Location |
|----|-----------------------|----------|
| AC-001 | adopted: `test_missing_file_gives_defaults` | `core/tests/test_config.py` |
| AC-002 | adopted: `test_file_overrides_only_given_keys` | `core/tests/test_config.py` |
| AC-003 | new: `test_unknown_table_and_key_are_rejected_by_name` | `core/tests/test_config_baseline.py` |
| AC-004 | new: `test_wrong_type_is_rejected_with_the_expected_type` | `core/tests/test_config_baseline.py` |
| AC-005 | adopted: `test_invalid_config_is_rejected`; new: `test_inconsistent_values_are_rejected` | `core/tests/test_config.py`, `core/tests/test_config_baseline.py` |
| AC-006 | adopted: `test_enforcement_defaults_to_enforce`, `test_enforcement_per_check_overrides_default` | `core/tests/test_config.py` |
| AC-007 | adopted: `test_guard_bash_always_enforces`; new: `test_unknown_check_names_always_enforce` | `core/tests/test_config.py`, `core/tests/test_config_baseline.py` |
| AC-008 | adopted: `test_rules_load_with_defaults`, `test_bad_rules_are_config_errors` | `core/tests/test_team_rules.py` |
| AC-009 | new: `test_jira_projects_are_validated_when_jira_is_not_required` | `core/tests/test_config_baseline.py` |
| AC-010 | adopted: `test_directory_named_like_config_is_an_error`; new: `test_invalid_toml_is_a_parse_error_with_the_path` | `core/tests/test_config.py`, `core/tests/test_config_baseline.py` |

## 6. Risks, rollout, rollback
No data, time or external service: every test writes an invented `lockstep.toml` into a temporary directory. The
defaults in AC-001 are literals in the test; a deliberate change to a default supersedes that criterion.

## 7. Open questions
None. Settled with the author on 2026-10-27: validating `jira.projects` without Jira (AC-009) and failing closed on
unknown check names (AC-007) are both intended.
