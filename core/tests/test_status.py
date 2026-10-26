import pytest

from lockstep_checks.config import load_config
from lockstep_checks.status import SpecStatusError, parse_status

CFG = load_config(__import__("pathlib").Path("/no-such-dir"))

VALID = """\
---
status: tests-locked   # draft | approved | tests-locked | implemented
pii: no
track: data
jira: MXAAI-123
locked_at_commit: 3f2a9c1
"""


def test_parses_valid_file():
    s = parse_status(VALID, CFG)
    assert s.status == "tests-locked"
    assert s.pii is False
    assert s.track == "data"
    assert s.jira == "MXAAI-123"
    assert s.locked_at_commit == "3f2a9c1"
    assert s.tests_locked is True


def test_draft_needs_no_jira_or_lock():
    s = parse_status("status: draft\npii: yes\ntrack: ai\njira:\nlocked_at_commit:\n", CFG)
    assert s.pii is True
    assert s.jira is None
    assert s.locked_at_commit is None
    assert s.tests_locked is False


def test_quoted_values_are_unquoted():
    s = parse_status("status: 'approved'\npii: \"no\"\ntrack: mixed\njira: MXAAI-9\n", CFG)
    assert s.status == "approved"
    assert s.pii is False


def test_design_step_is_optional_and_off_by_default():
    assert parse_status("status: draft\npii: no\ntrack: data\n", CFG).design is False
    assert parse_status("status: draft\npii: no\ntrack: data\ndesign: yes\n", CFG).design is True


def test_implemented_counts_as_locked():
    text = VALID.replace("tests-locked", "implemented", 1)
    assert parse_status(text, CFG).tests_locked is True


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("pii: no\ntrack: data\n", "status"),
        ("status: done\npii: no\ntrack: data\n", "status"),
        ("status: draft\npii: true\ntrack: data\n", "pii"),
        ("status: draft\npii: no\ntrack: web\n", "track"),
        ("status: draft\npii: no\ntrack: data\nowner: x\n", "owner"),
        ("status: draft\nstatus: approved\npii: no\ntrack: data\n", "twice"),
        ("status: draft\npii: no\ntrack: data\njira: mxaai-1\n", "jira"),
        ("status: approved\npii: no\ntrack: data\n", "jira"),
        ("status: tests-locked\npii: no\ntrack: data\njira: MXAAI-1\n", "locked_at_commit"),
        ("status: tests-locked\npii: no\ntrack: data\njira: MXAAI-1\nlocked_at_commit: main\n", "locked_at_commit"),
        ("status: draft\npii: no\ntrack:\n  - data\n", "line 4"),
        ("status: [draft]\npii: no\ntrack: data\n", "status"),
        ("status: draft\npii: no\ntrack: data\ndesign: maybe\n", "design"),
    ],
)
def test_invalid_status_is_rejected(text, fragment):
    with pytest.raises(SpecStatusError, match=fragment):
        parse_status(text, CFG)


def test_track_must_be_enabled_in_config(tmp_path):
    (tmp_path / "lockstep.toml").write_text('[lockstep]\ntracks = ["data"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    parse_status("status: draft\npii: no\ntrack: data\n", cfg)
    for track in ("ai", "mixed"):
        with pytest.raises(SpecStatusError, match="track"):
            parse_status(f"status: draft\npii: no\ntrack: {track}\n", cfg)


def test_jira_key_must_belong_to_a_configured_project(tmp_path):
    (tmp_path / "lockstep.toml").write_text('[jira]\nprojects = ["MXAAI", "OPS"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    for key in ("MXAAI-1", "OPS-22"):
        assert parse_status(f"status: approved\npii: no\ntrack: data\njira: {key}\n", cfg).jira == key
    for key in ("PROJ-1", "MXAAI-123-x", "XOPS-1", "mxaai-1", "MXAAI-0"):
        with pytest.raises(SpecStatusError, match="jira"):
            parse_status(f"status: approved\npii: no\ntrack: data\njira: {key}\n", cfg)


def test_approved_needs_no_jira_when_jira_is_optional(tmp_path):
    (tmp_path / "lockstep.toml").write_text("[jira]\nrequired = false\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert parse_status("status: approved\npii: no\ntrack: data\njira:\n", cfg).jira is None
    with pytest.raises(SpecStatusError, match="jira"):
        parse_status("status: approved\npii: no\ntrack: data\njira: mxaai-1\n", cfg)
