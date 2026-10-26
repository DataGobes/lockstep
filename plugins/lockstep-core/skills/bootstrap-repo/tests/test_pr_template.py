"""Spec 0001: the PR template points to the trust summary instead of a hand-filled AC table (AC-021)."""

from pathlib import Path

import pytest

LOCKSTEP = Path(__file__).resolve().parents[5]
TEMPLATE = LOCKSTEP / "templates" / "azuredevops" / "pull_request_template.md"


@pytest.mark.ac("0001/AC-021")
def test_template_points_to_the_lockstep_summary_comment():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "Lockstep summary" in text


@pytest.mark.ac("0001/AC-021")
def test_template_has_no_hand_filled_ac_table():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "## AC → test → result" not in text
    assert "| AC | Test | Result |" not in text
