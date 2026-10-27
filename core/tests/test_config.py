from dataclasses import replace
from pathlib import Path

import pytest

from lockstep_checks.config import ConfigError, Enforcement, load_config

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "lockstep.toml"


def write(tmp_path: Path, text: str) -> Path:
    (tmp_path / "lockstep.toml").write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.ac("0002/AC-001")
def test_missing_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.source is None
    assert cfg.specs_dir == "specs"
    assert cfg.pr_size.warn_lines == 400
    assert cfg.pr_size.fail_lines == 800
    assert cfg.pr_size.max_files == 100
    assert "tests/**" in cfg.protect.globs


@pytest.mark.ac("0002/AC-002")
def test_file_overrides_only_given_keys(tmp_path):
    cfg = load_config(write(tmp_path, "[pr_size]\nwarn_lines = 300\n"))
    assert cfg.source == tmp_path / "lockstep.toml"
    assert cfg.pr_size.warn_lines == 300
    assert cfg.pr_size.fail_lines == 800


def test_template_loads_and_matches_defaults():
    # The template documents the defaults; if they drift apart, one of them is lying.
    # The one deliberate difference: new repos start in warn mode, a repo without the table enforces.
    cfg = load_config(TEMPLATE.parent)
    assert cfg.source == TEMPLATE
    assert cfg.enforcement == Enforcement(default="warn")
    defaults = load_config(TEMPLATE.parent / "no-such-dir")
    assert replace(cfg, enforcement=Enforcement()).without_source() == defaults.without_source()


@pytest.mark.ac("0002/AC-006")
def test_enforcement_defaults_to_enforce(tmp_path):
    e = load_config(tmp_path).enforcement
    assert e.mode("protect_tests") == "enforce"
    assert e.mode("check_test_tamper") == "enforce"


@pytest.mark.ac("0002/AC-006")
def test_enforcement_per_check_overrides_default(tmp_path):
    e = load_config(write(tmp_path, '[enforcement]\ndefault = "warn"\ntest_tamper = "enforce"\n')).enforcement
    assert e.mode("check_test_tamper") == "enforce"
    assert e.mode("check_pr_size") == "warn"
    assert e.mode("protect_tests") == "warn"


@pytest.mark.ac("0002/AC-007")
def test_guard_bash_always_enforces(tmp_path):
    e = load_config(write(tmp_path, '[enforcement]\ndefault = "warn"\n')).enforcement
    assert e.mode("guard_bash") == "enforce"
    assert e.mode("default") == "enforce"


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("[pr_size]\nwarn_line = 300\n", "pr_size.warn_line"),  # typo must not silently disable a gate
        ("[nonsense]\nx = 1\n", "nonsense"),
        ('[pr_size]\nwarn_lines = "400"\n', "pr_size.warn_lines"),
        ("[pr_size]\nwarn_lines = 900\nfail_lines = 800\n", "warn_lines"),
        ("[pr_size]\nmax_files = 101\n", "max_files"),
        ('[lockstep]\nbranch_pattern = "feature/(\\\\d+)"\n', "id"),
        ('[lockstep]\nbranch_pattern = "("\n', "branch_pattern"),
        ('[lockstep]\ntracks = ["data", "web"]\n', "tracks"),
        ('[lockstep]\ntracks = ["data", "data"]\n', "tracks"),
        ('[protect]\nglobs = "tests/**"\n', "protect.globs"),
        ('[jira]\nprojects = ["mxaai"]\n', "jira.projects"),
        ("[jira]\nprojects = []\n", "jira.projects"),
        ('[jira]\nprojects = ["MXAAI", "MXAAI"]\n', "jira.projects"),
        ('[jira]\nkey_pattern = "X-1"\n', "jira.key_pattern"),
        ('[enforcement]\ndefault = "off"\n', "enforcement.default"),
        ('[enforcement]\ndefault = ""\n', "enforcement.default"),
        ('[enforcement]\npr_size = "block"\n', "enforcement.pr_size"),
        ('[enforcement]\nguard_bash = "warn"\n', "enforcement.guard_bash"),  # never configurable
        ('[specs]\nac_format = "gherkin"\n', "specs.ac_format"),
        ("[specs]\ndesign_from_criteria = -1\n", "specs.design_from_criteria"),
        ("this is not toml", "lockstep.toml"),
    ],
)
@pytest.mark.ac("0002/AC-005")
def test_invalid_config_is_rejected(tmp_path, text, fragment):
    with pytest.raises(ConfigError, match=fragment.replace("(", r"\(")):
        load_config(write(tmp_path, text))


def test_branch_regex_is_compiled(tmp_path):
    cfg = load_config(tmp_path)
    m = cfg.branch_regex.match("feature/0042-churn-features")
    assert m and m.group("id") == "0042"


@pytest.mark.ac("0002/AC-010")
def test_directory_named_like_config_is_an_error(tmp_path):
    (tmp_path / "lockstep.toml").mkdir()
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path)


def test_default_jira_project_is_mxaai(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.jira_projects == ("MXAAI",)
    assert cfg.jira_key_regex.search("MXAAI-42 Add churn features").group() == "MXAAI-42"
    assert cfg.jira_key_regex.search("feature/0042-mxaai-42") is None
