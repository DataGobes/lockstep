"""Unit tests for trim_pipeline, the piece of spec 0003 that removes the job blocks of tracks a repo did not choose."""

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bootstrap_trim", HERE.parent / "scripts" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
sys.modules["bootstrap_trim"] = bootstrap
spec.loader.exec_module(bootstrap)

PIPELINE = """\
stages:
  - stage: checks
    jobs:
      - job: lockstep
        steps: []

      - job: dbt
        steps: []

      - job: bundle
        steps: []

      - job: evals
        steps: []

  - stage: summary
"""


@pytest.mark.ac("0003/AC-001")
def test_ai_only_removes_the_data_jobs_with_their_blank_line():
    assert bootstrap.trim_pipeline(PIPELINE, ["ai"]) == (
        "stages:\n  - stage: checks\n    jobs:\n      - job: lockstep\n        steps: []\n\n"
        "      - job: evals\n        steps: []\n\n  - stage: summary\n"
    )


@pytest.mark.ac("0003/AC-002")
def test_data_only_removes_the_evals_job_with_its_blank_line():
    assert bootstrap.trim_pipeline(PIPELINE, ["data"]) == (
        "stages:\n  - stage: checks\n    jobs:\n      - job: lockstep\n        steps: []\n\n"
        "      - job: dbt\n        steps: []\n\n      - job: bundle\n        steps: []\n\n  - stage: summary\n"
    )


@pytest.mark.ac("0003/AC-003")
def test_both_tracks_leave_the_text_alone():
    assert bootstrap.trim_pipeline(PIPELINE, ["ai", "data"]) == PIPELINE


@pytest.mark.ac("0003/AC-001")
def test_a_job_whose_name_only_starts_like_a_track_job_stays():
    text = "    jobs:\n      - job: dbt_docs\n        steps: []\n\n"
    assert bootstrap.trim_pipeline(text, ["ai"]) == text


@pytest.mark.ac("0003/AC-001")
def test_job_lines_with_crlf_or_trailing_spaces_are_still_trimmed():
    crlf = "    jobs:\r\n      - job: dbt\r\n        steps: []\r\n\r\n      - job: evals\r\n"
    assert bootstrap.trim_pipeline(crlf, ["ai"]) == "    jobs:\r\n      - job: evals\r\n"
    spaced = "    jobs:\n      - job: bundle  \n        steps: []\n\n      - job: evals\n"
    assert bootstrap.trim_pipeline(spaced, ["ai"]) == "    jobs:\n      - job: evals\n"
