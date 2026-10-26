"""Spec 0001: posting the trust summary on the Azure DevOps PR."""

from pathlib import Path

import pytest

from lockstep_checks.trust_summary import MARKER, AdoError, Summary, post, publish

ROOT = Path(__file__).resolve().parents[2]


class FakeThreads:
    """An in-memory Pull Request Threads API."""

    def __init__(self, threads=None, fail=None):
        self.threads = threads or []
        self.fail = fail
        self.created = []
        self.updated = []

    def list_threads(self):
        if self.fail:
            raise self.fail
        return self.threads

    def create_thread(self, content, status):
        if self.fail:
            raise self.fail
        thread = {"id": 100 + len(self.threads), "status": status, "comments": [{"id": 1, "content": content}]}
        self.threads.append(thread)
        self.created.append(thread)
        return thread

    def update_comment(self, thread_id, comment_id, content):
        if self.fail:
            raise self.fail
        self.updated.append((thread_id, comment_id, content))
        for t in self.threads:
            if t["id"] == thread_id:
                for c in t["comments"]:
                    if c["id"] == comment_id:
                        c["content"] = content


def summary(text="All 3 signals clean: 3 of 3 criteria have a passing test."):
    return Summary(markdown=f"{MARKER}\n{text}\n", data={"schema_version": 1})


@pytest.mark.ac("0001/AC-001")
def test_posts_a_summary_comment_on_a_pr_without_one():
    client = FakeThreads(threads=[{"id": 7, "status": "active", "comments": [{"id": 1, "content": "Looks good"}]}])
    result = post(summary(), client)
    assert result.action == "created"
    assert len(client.created) == 1
    assert MARKER in client.created[0]["comments"][0]["content"]


@pytest.mark.ac("0001/AC-001")
def test_the_summary_job_runs_whether_the_other_jobs_passed_or_failed():
    template = ROOT / "core" / "pipelines" / "trust-summary.yml"
    assert template.is_file(), "core/pipelines/trust-summary.yml is missing"
    text = template.read_text(encoding="utf-8")
    assert "condition: always()" in text
    assert "python -m lockstep_checks.trust_summary" in text
    root = (ROOT / "templates" / "azure-pipelines-pr.yml").read_text(encoding="utf-8")
    assert ".lockstep/pipelines/trust-summary.yml" in root


@pytest.mark.ac("0001/AC-002")
def test_a_later_run_replaces_the_text_of_the_same_comment():
    client = FakeThreads()
    first = post(summary("1 of 3 criteria have a passing test."), client)
    second = post(summary("All 3 signals clean: 3 of 3 criteria have a passing test."), client)
    assert second.action == "updated"
    assert second.thread_id == first.thread_id
    assert len(client.created) == 1
    assert client.updated == [(first.thread_id, 1, summary().markdown)]


@pytest.mark.ac("0001/AC-002")
def test_finds_its_own_comment_among_others():
    threads = [
        {"id": 7, "status": "active", "comments": [{"id": 1, "content": "Please rename this"}]},
        {"id": 9, "status": "closed", "comments": [{"id": 1, "content": f"{MARKER}\nold summary"}]},
    ]
    client = FakeThreads(threads=threads)
    result = post(summary(), client)
    assert (result.action, result.thread_id) == ("updated", 9)
    assert client.created == []


@pytest.mark.ac("0001/AC-003")
def test_the_thread_is_created_closed():
    client = FakeThreads()
    post(summary(), client)
    assert client.created[0]["status"] == "closed"


@pytest.mark.ac("0001/AC-016")
@pytest.mark.parametrize(
    ("error", "cause"),
    [(AdoError(403, "TF401027: permission denied"), "Contribute to pull requests"), (AdoError(500, "busy"), "500")],
)
def test_a_failed_post_warns_keeps_the_artifact_and_succeeds(tmp_path, capsys, error, cause):
    s = summary()
    code = publish(s, FakeThreads(fail=error), tmp_path, out=None)
    out = capsys.readouterr().out
    assert code == 0
    assert "##vso[task.logissue type=warning]" in out
    assert cause in out
    saved = list(tmp_path.glob("*.md"))
    assert len(saved) == 1 and saved[0].read_text(encoding="utf-8") == s.markdown


@pytest.mark.ac("0001/AC-016")
def test_a_successful_post_also_keeps_the_artifact(tmp_path, capsys):
    s = summary()
    assert publish(s, FakeThreads(), tmp_path, out=None) == 0
    assert [p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")] == [s.markdown]
