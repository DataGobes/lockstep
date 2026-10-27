import json

from lockstep_checks import ci
from lockstep_checks.gitdiff import base_ref
from lockstep_checks.lock import branch_tip
from lockstep_checks.spec import current_branch

AZURE = {
    "TF_BUILD": "True",
    "SYSTEM_PULLREQUEST_TARGETBRANCH": "refs/heads/main",
    "SYSTEM_PULLREQUEST_SOURCEBRANCH": "refs/heads/feature/0042-churn",
    "SYSTEM_PULLREQUEST_SOURCECOMMITID": "abc1234",
    "BUILD_SOURCEBRANCH": "refs/pull/7/merge",
}


def github(tmp_path, head_sha="def5678"):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"head": {"sha": head_sha}}}), encoding="utf-8")
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_BASE_REF": "main",
        "GITHUB_HEAD_REF": "feat/w1.2-data-ingestion",
        "GITHUB_REF": "refs/pull/7/merge",
        "GITHUB_EVENT_PATH": str(event),
    }


def test_azure_pr_build():
    assert ci.on_azure(AZURE) and not ci.on_github(AZURE)
    assert ci.target_branch(AZURE) == "main"
    assert ci.source_branch(AZURE) == "feature/0042-churn"
    assert ci.source_commit(AZURE) == "abc1234"


def test_github_pr_build(tmp_path):
    env = github(tmp_path)
    assert ci.on_github(env) and not ci.on_azure(env)
    assert ci.target_branch(env) == "main"
    assert ci.source_branch(env) == "feat/w1.2-data-ingestion"
    assert ci.source_commit(env) == "def5678"


def test_github_push_build_has_a_branch_but_no_pr():
    env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_BASE_REF": "", "GITHUB_HEAD_REF": ""}
    assert ci.source_branch(env) == "main"
    assert ci.target_branch(env) == ""
    assert ci.source_commit(env) == ""


def test_github_tag_build_names_no_branch():
    assert ci.source_branch({"GITHUB_REF": "refs/tags/v1"}) == ""


def test_unreadable_github_event_falls_back(tmp_path):
    env = github(tmp_path)
    env["GITHUB_EVENT_PATH"] = str(tmp_path / "missing.json")
    assert ci.source_commit(env) == ""
    (tmp_path / "bad.json").write_text('{"pull_request": null}', encoding="utf-8")
    env["GITHUB_EVENT_PATH"] = str(tmp_path / "bad.json")
    assert ci.source_commit(env) == ""


def test_outside_ci_everything_is_empty():
    assert (ci.target_branch({}), ci.source_branch({}), ci.source_commit({})) == ("", "", "")
    assert not ci.on_azure({}) and not ci.on_github({})


def test_callers_read_github_variables(tmp_path):
    env = github(tmp_path)
    assert base_ref(None, env) == "origin/main"
    assert current_branch(tmp_path, env) == "feat/w1.2-data-ingestion"
    assert branch_tip(env) == "def5678"
