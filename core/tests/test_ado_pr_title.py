import io
import json
import re
import urllib.error
from pathlib import Path

import pytest

from lockstep_checks.ado_pr_title import TitleError, fetch_title, main, pr_url, set_variable_command

ROOT = Path(__file__).resolve().parents[2]

ENV = {
    "SYSTEM_COLLECTIONURI": "https://dev.azure.com/example-org/",
    "SYSTEM_TEAMPROJECTID": "11111111-2222-3333-4444-555555555555",
    "BUILD_REPOSITORY_ID": "66666666-7777-8888-9999-000000000000",
    "SYSTEM_PULLREQUEST_PULLREQUESTID": "42",
    "SYSTEM_ACCESSTOKEN": "token",
}


def reply(title):
    calls = []

    def fetch(req):
        calls.append(req)
        return json.dumps({"pullRequestId": 42, "title": title}).encode()

    return fetch, calls


def test_url_uses_ids_not_names():
    assert pr_url(ENV) == (
        "https://dev.azure.com/example-org/11111111-2222-3333-4444-555555555555/_apis/git/repositories/"
        "66666666-7777-8888-9999-000000000000/pullRequests/42?api-version=7.1"
    )


def test_sets_the_variable_for_later_steps():
    fetch, calls = reply("[test-change] MXAAI-42 Fix fixture dates")
    out = io.StringIO()
    assert main(ENV, out, fetch) == 0
    assert (
        out.getvalue().splitlines()[0]
        == "##vso[task.setvariable variable=LOCKSTEP_PR_TITLE][test-change] MXAAI-42 Fix fixture dates"
    )
    assert calls[0].get_header("Authorization") == "Bearer token"


def test_a_line_break_cannot_start_a_second_command():
    cmd = set_variable_command("MXAAI-1 x\n##vso[task.setvariable variable=SYSTEM_ACCESSTOKEN]stolen")
    assert "\n" not in cmd
    assert cmd.count("##vso[") == 2  # the second one is inside the value, which the agent does not parse


def test_not_a_pr_build_does_nothing():
    out = io.StringIO()
    env = {k: v for k, v in ENV.items() if k != "SYSTEM_PULLREQUEST_PULLREQUESTID"}
    assert main(env, out, fetch=lambda req: pytest.fail("must not call the API")) == 0
    assert "not a PR build" in out.getvalue()


def test_missing_token_explains_the_mapping():
    env = {k: v for k, v in ENV.items() if k != "SYSTEM_ACCESSTOKEN"}
    with pytest.raises(TitleError, match=r"\$\(System.AccessToken\)"):
        fetch_title(env, fetch=lambda req: b"")


def test_api_errors_fail_the_step():
    def forbidden(req):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    out = io.StringIO()
    assert main(ENV, out, forbidden) == 1
    assert out.getvalue().startswith("##vso[task.logissue type=error]ado_pr_title: Azure DevOps API returned 403")


@pytest.mark.parametrize("body", [b"<html>", b"{}", b'{"title": 7}'])
def test_unexpected_reply_fails(body):
    with pytest.raises(TitleError, match="unexpected reply"):
        fetch_title(ENV, fetch=lambda req: body)


def test_pipeline_template_runs_every_check_module():
    # The template names checks by suffix; a typo there would only show up in a real pipeline run.
    text = (ROOT / "core" / "pipelines" / "lockstep-pr.yml").read_text(encoding="utf-8")
    checks = re.search(r"^    default: \[(?P<names>[a-z_, ]+)\]$", text, re.MULTILINE)["names"].split(", ")
    modules = {p.stem.removeprefix("check_") for p in (ROOT / "core" / "src" / "lockstep_checks").glob("check_*.py")}
    assert sorted(checks) == sorted(modules)
    assert "fetchDepth: 0" in text
