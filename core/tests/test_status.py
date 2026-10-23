import pytest

from codefactory.config import load_config
from codefactory.status import SpecStatusError, parse_status

CFG = load_config(__import__("pathlib").Path("/no-such-dir"))

VALID = """\
---
status: tests-locked   # draft | approved | tests-locked | implemented
pii: no
track: data
jira: PROJ-123
locked_at_commit: 3f2a9c1
"""


def test_parses_valid_file():
    s = parse_status(VALID, CFG)
    assert s.status == "tests-locked"
    assert s.pii is False
    assert s.track == "data"
    assert s.jira == "PROJ-123"
    assert s.locked_at_commit == "3f2a9c1"
    assert s.tests_locked is True


def test_draft_needs_no_jira_or_lock():
    s = parse_status("status: draft\npii: yes\ntrack: ai\njira:\nlocked_at_commit:\n", CFG)
    assert s.pii is True
    assert s.jira is None
    assert s.locked_at_commit is None
    assert s.tests_locked is False


def test_quoted_values_are_unquoted():
    s = parse_status("status: 'approved'\npii: \"no\"\ntrack: mixed\njira: PROJ-9\n", CFG)
    assert s.status == "approved"
    assert s.pii is False


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
        ("status: draft\npii: no\ntrack: data\njira: proj-1\n", "jira"),
        ("status: approved\npii: no\ntrack: data\n", "jira"),
        ("status: tests-locked\npii: no\ntrack: data\njira: PROJ-1\n", "locked_at_commit"),
        ("status: tests-locked\npii: no\ntrack: data\njira: PROJ-1\nlocked_at_commit: main\n", "locked_at_commit"),
        ("status: draft\npii: no\ntrack:\n  - data\n", "line 4"),
        ("status: [draft]\npii: no\ntrack: data\n", "status"),
    ],
)
def test_invalid_status_is_rejected(text, fragment):
    with pytest.raises(SpecStatusError, match=fragment):
        parse_status(text, CFG)


def test_track_must_be_enabled_in_config(tmp_path):
    (tmp_path / "factory.toml").write_text('[factory]\ntracks = ["data"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    parse_status("status: draft\npii: no\ntrack: data\n", cfg)
    for track in ("ai", "mixed"):
        with pytest.raises(SpecStatusError, match="track"):
            parse_status(f"status: draft\npii: no\ntrack: {track}\n", cfg)
