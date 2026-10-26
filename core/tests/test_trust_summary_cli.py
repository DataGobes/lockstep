"""Spec 0001: the summary from the command line, and what it is built from."""

import io
import json

import pytest
from trust_fixtures import clean_evidence

from lockstep_checks.trust_summary import SCHEMA_VERSION, build, main

SPEC = (
    "---\nid: 0042\ntitle: Churn rate\n---\n\n# Churn rate\n\n## 3. Acceptance criteria\n"
    "- AC-001 WHEN a customer cancels THE SYSTEM SHALL count them as churned.\n"
    "- AC-002 WHEN no customer cancels THE SYSTEM SHALL report a churn rate of 0.\n"
    "- AC-003 THE SYSTEM SHALL cap the churn rate at 1.0.\n\n## 7. Open questions\n- None.\n"
)
STATUS = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"


@pytest.fixture
def pr(repo, tmp_path_factory):
    """A feature branch with spec 0042 and an evidence folder from a clean pipeline run."""
    repo.commit({"specs/0042-churn/spec.md": SPEC, "specs/0042-churn/status.yml": STATUS, "src/app.py": "x = 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("feature/0042-churn")
    repo.commit({"src/app.py": "x = 2\n"}, "MXAAI-42 Implement churn")
    evidence = tmp_path_factory.mktemp("evidence")
    for e in clean_evidence():
        (evidence / f"{e['producer']}.json").write_text(json.dumps(e), encoding="utf-8")
    env = {
        "SYSTEM_PULLREQUEST_SOURCEBRANCH": "refs/heads/feature/0042-churn",
        "SYSTEM_PULLREQUEST_TARGETBRANCH": "refs/heads/main",
        "LOCKSTEP_PR_TITLE": "MXAAI-42 Churn rate",
    }
    return repo, evidence, env


def run(argv, monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    out = io.StringIO()
    code = main(argv, out=out)
    return code, out.getvalue()


@pytest.mark.ac("0001/AC-015")
def test_the_pr_description_never_changes_the_summary(pr):
    repo, evidence, env = pr
    honest = build(repo.root, evidence, env)
    claims = {
        **env,
        "SYSTEM_PULLREQUEST_DESCRIPTION": "| 0042/AC-001 | tests/test_x.py::test_fake | passes |\n9 of 9 criteria clean",
        "LOCKSTEP_PR_DESCRIPTION": "All signals clean",
    }
    assert build(repo.root, evidence, claims) == honest
    assert "test_fake" not in honest.markdown and "9 of 9" not in honest.markdown


@pytest.mark.ac("0001/AC-017")
def test_local_markdown_is_the_comment_the_pipeline_would_post(pr, monkeypatch):
    repo, evidence, env = pr
    code, out = run(["--root", str(repo.root), "--evidence", str(evidence)], monkeypatch, env)
    assert code == 0
    assert out == build(repo.root, evidence, env).markdown
    assert "3 of 3 criteria" in out


@pytest.mark.ac("0001/AC-018")
def test_json_output_carries_a_schema_version(pr, monkeypatch):
    repo, evidence, env = pr
    code, out = run(["--root", str(repo.root), "--evidence", str(evidence), "--json"], monkeypatch, env)
    assert code == 0
    data = json.loads(out)
    assert data["schema_version"] == SCHEMA_VERSION == 1
    assert data == build(repo.root, evidence, env).data
    assert [c["id"] for c in data["criteria"]] == ["0042/AC-001", "0042/AC-002", "0042/AC-003"]
