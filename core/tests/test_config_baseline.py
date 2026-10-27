"""Baseline 0002: what loading lockstep.toml does today. Every expected value was observed by running the code once."""

import re
from pathlib import Path

import pytest

from lockstep_checks.config import ConfigError, load_config


def write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "lockstep.toml").write_text(text, encoding="utf-8")
    return tmp_path


def rejected(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(write(tmp_path, text))


@pytest.mark.ac("0002/AC-003")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[nonsense]\nx = 1\n", "unknown table [nonsense]"),
        ("[pr_size]\nwarn_line = 300\n", "unknown key pr_size.warn_line"),
        ('[lockstep]\nspec_dir = "specs"\n', "unknown key lockstep.spec_dir"),
        ('[enforcement]\nguard_bash = "warn"\n', "unknown key enforcement.guard_bash"),
    ],
)
def test_unknown_table_and_key_are_rejected_by_name(tmp_path, text, message):
    rejected(tmp_path, text, message)


@pytest.mark.ac("0002/AC-004")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[pr_size]\nwarn_lines = true\n", "pr_size.warn_lines must be int, got bool"),
        ('[pr_size]\nwarn_lines = "400"\n', "pr_size.warn_lines must be int, got str"),
        ('[jira]\nrequired = "no"\n', "jira.required must be bool, got str"),
        ("[lockstep]\nspecs_dir = 1\n", "lockstep.specs_dir must be str, got int"),
        ('[protect]\nglobs = "tests/**"\n', "protect.globs must be a list of strings"),
        ("[lockstep]\ntracks = [1]\n", "lockstep.tracks must be a list of strings"),
    ],
)
def test_wrong_type_is_rejected_with_the_expected_type(tmp_path, text, message):
    rejected(tmp_path, text, message)


@pytest.mark.ac("0002/AC-005")
@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[lockstep]\ntracks = []\n", "tracks must be a non-empty subset of ['data', 'ai'] without duplicates, got []"),
        ("[pr_size]\nwarn_lines = 0\n", "pr_size needs 0 < warn_lines <= fail_lines"),
        ("[pr_size]\nmax_files = 0\n", "pr_size.max_files must be 1-100 (Copilot code review limit)"),
        (
            '[lanes]\nchore = ["chore/"]\nbugfix = ["chore/"]\n',
            "lanes.chore, lanes.bugfix and lanes.feature must be distinct branch prefixes ending in '/'",
        ),
        (
            '[lanes]\nchore = ["chore"]\n',
            "lanes.chore, lanes.bugfix and lanes.feature must be distinct branch prefixes ending in '/'",
        ),
        (
            "[specs]\nspec_pr_above_criteria = -1\n",
            "specs.spec_pr_above_criteria must be 0 (every spec gets a spec PR) or more",
        ),
        (
            '[specs]\nspec_pr_for = ["design", "size"]\n',
            "specs.spec_pr_for must be distinct values from ['design', 'contract', 'pii'], got ['design', 'size']",
        ),
        (
            '[specs]\nspec_pr_for = ["pii", "pii"]\n',
            "specs.spec_pr_for must be distinct values from ['design', 'contract', 'pii'], got ['pii', 'pii']",
        ),
    ],
)
def test_inconsistent_values_are_rejected(tmp_path, text, message):
    rejected(tmp_path, text, message)


@pytest.mark.ac("0002/AC-007")
def test_unknown_check_names_always_enforce(tmp_path):
    e = load_config(write(tmp_path, '[enforcement]\ndefault = "warn"\n')).enforcement
    assert e.mode("pr_size") == "warn"
    assert e.mode("nonsense") == "enforce"
    assert e.mode("check_nonsense") == "enforce"
    assert e.mode("check_default") == "enforce"


@pytest.mark.ac("0002/AC-009")
def test_jira_projects_are_validated_when_jira_is_not_required(tmp_path):
    cfg = load_config(write(tmp_path, "[jira]\nrequired = false\n"))
    assert cfg.jira_required is False
    assert cfg.jira_projects == ("MXAAI",)

    empty = "[jira]\nrequired = false\nprojects = []\n"
    rejected(tmp_path, empty, "jira.projects must be distinct Jira project keys such as MXAAI, got []")
    lower = '[jira]\nrequired = false\nprojects = ["mxaai"]\n'
    rejected(tmp_path, lower, "jira.projects must be distinct Jira project keys such as MXAAI, got ['mxaai']")


@pytest.mark.ac("0002/AC-010")
def test_invalid_toml_is_a_parse_error_with_the_path(tmp_path):
    root = write(tmp_path, "this is not toml")
    with pytest.raises(ConfigError) as info:
        load_config(root)
    assert str(info.value).startswith(f"{root / 'lockstep.toml'}: cannot parse lockstep.toml: ")
