"""Spec 0003: bootstrap trims the PR pipeline's jobs to the chosen tracks.

Expected files are cut from the template between literal job and stage lines; the tests never call the trimming code
to build what they expect.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
TEMPLATE = (LOCKSTEP / "templates" / "azure-pipelines-pr.yml").read_text(encoding="utf-8")
PIPELINE = "azure-pipelines-pr.yml"

spec = importlib.util.spec_from_file_location("bootstrap_0003", HERE.parent / "scripts" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
sys.modules["bootstrap_0003"] = bootstrap
spec.loader.exec_module(bootstrap)

DBT = "      - job: dbt\n"
EVALS = "      - job: evals\n"
SUMMARY = "  - stage: summary\n"


def without(start: str, stop: str) -> str:
    """The template minus the lines from `start` up to, not including, `stop`."""
    lines = TEMPLATE.splitlines(keepends=True)
    i, j = lines.index(start), lines.index(stop)
    return "".join(lines[:i] + lines[j:])


AI_ONLY = without(DBT, EVALS)  # drops the dbt and bundle job blocks
DATA_ONLY = without(EVALS, SUMMARY)  # drops the evals job block

# A repo's own pipeline, written by hand before Lockstep: no track jobs at all.
OWN_PIPELINE = """\
trigger: none

stages:
  - stage: checks
    jobs:
      - job: lockstep
        steps:
          - template: .lockstep/pipelines/lockstep-pr.yml
"""


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def planned(repo: Path, tracks: list[str]) -> bootstrap.Action:
    actions = bootstrap.plan(repo, LOCKSTEP, "source: test\n", tracks, ["MXAAI"])
    return next(a for a in actions if a.path == PIPELINE)


def test_the_expected_files_are_what_the_spec_describes():
    # Guards the literal cuts above against a template edit, so a red test below means missing behaviour.
    assert "- job: dbt" not in AI_ONLY and "- job: bundle" not in AI_ONLY and "- job: evals" in AI_ONLY
    assert "- job: evals" not in DATA_ONLY and "- job: dbt" in DATA_ONLY and "- job: bundle" in DATA_ONLY
    assert "\n\n\n" not in AI_ONLY and "\n\n\n" not in DATA_ONLY


@pytest.mark.ac("0003/AC-001")
def test_ai_track_drops_the_dbt_and_bundle_jobs(repo):
    action = planned(repo, ["ai"])
    assert action.kind == "create"
    assert action.content.decode() == AI_ONLY


@pytest.mark.ac("0003/AC-002")
def test_data_track_drops_the_evals_job(repo):
    action = planned(repo, ["data"])
    assert action.kind == "create"
    assert action.content.decode() == DATA_ONLY


@pytest.mark.ac("0003/AC-003")
@pytest.mark.parametrize("tracks", [["data", "ai"], ["ai", "data"]], ids=["data,ai", "ai,data"])
def test_both_tracks_keep_the_template_as_it_is(repo, tracks):
    assert planned(repo, tracks).content.decode() == TEMPLATE


@pytest.mark.ac("0003/AC-003")
def test_default_tracks_write_the_template_as_it_is(repo):
    assert bootstrap.main(["--root", str(repo), "--source", str(LOCKSTEP), "--apply"]) == 0
    assert (repo / PIPELINE).read_text(encoding="utf-8") == TEMPLATE


@pytest.mark.ac("0003/AC-004")
def test_a_repo_file_that_differs_from_the_trimmed_template_is_a_merge_item(repo):
    # A repo bootstrapped before this spec holds the full template; with one track it now differs.
    (repo / PIPELINE).write_text(TEMPLATE, encoding="utf-8")
    assert planned(repo, ["ai"]).kind == "merge"
    assert bootstrap.main(["--root", str(repo), "--source", str(LOCKSTEP), "--tracks", "ai", "--apply"]) == 0
    assert (repo / PIPELINE).read_text(encoding="utf-8") == TEMPLATE


@pytest.mark.ac("0003/AC-005")
@pytest.mark.parametrize(("tracks", "earlier"), [(["ai"], AI_ONLY), (["data"], DATA_ONLY)], ids=["ai", "data"])
def test_the_file_an_earlier_run_created_is_up_to_date(repo, tracks, earlier):
    (repo / PIPELINE).write_text(earlier, encoding="utf-8")
    assert planned(repo, tracks).kind == "same"


@pytest.mark.ac("0003/AC-006")
def test_the_merge_diff_proposes_only_the_chosen_tracks_jobs(repo, capsys):
    (repo / PIPELINE).write_text(OWN_PIPELINE, encoding="utf-8")
    assert bootstrap.main(["--root", str(repo), "--source", str(LOCKSTEP), "--tracks", "ai", "--diff"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert f"merge   {PIPELINE}" in out
    assert "+      - job: evals" in out
    assert "+      - job: dbt" not in out
    assert "+      - job: bundle" not in out
