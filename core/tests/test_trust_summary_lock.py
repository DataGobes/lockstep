"""Spec 0001: the lock evidence, from git history (AC-008)."""

import pytest

from lockstep_checks.trust_summary import lock_evidence

APPROVED = "status: approved\npii: no\ntrack: data\njira: MXAAI-42\n"
LOCKED = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"
RED = "from app import churn\n\ndef test_churn():\n    assert churn() == 3\n"


def locked_feature_branch(repo):
    """main has an approved spec; the test PR adds red tests and the lock, then merges into the feature branch."""
    repo.commit(
        {"src/app.py": "def churn():\n    raise NotImplementedError\n", "specs/0042-churn/status.yml": APPROVED}
    )
    repo.branch("feature/0042-churn")
    repo.branch("test/0042-churn")
    repo.commit({"tests/test_churn.py": RED}, "MXAAI-42 Add failing tests for spec 0042")
    repo.commit({"specs/0042-churn/status.yml": LOCKED}, "MXAAI-42 Lock tests")
    repo.git("checkout", "-q", "feature/0042-churn")
    repo.git("merge", "-q", "--no-ff", "-m", "Merged PR 7: tests for 0042", "test/0042-churn")
    return repo.git("rev-parse", "HEAD").strip()


@pytest.mark.ac("0001/AC-008")
def test_names_the_lock_commit_and_its_date(repo):
    sha = locked_feature_branch(repo)
    repo.commit({"src/app.py": "def churn():\n    return 3\n"}, "MXAAI-42 Implement churn")
    date = repo.git("show", "-s", "--format=%cs", sha).strip()
    ev = lock_evidence(repo.root, "main", "feature/0042-churn")
    assert ev["producer"] == "lock" and ev["status"] == "measured"
    assert ev["signals"]["lock"] == {"commit": sha, "date": date, "changed_since": []}


@pytest.mark.ac("0001/AC-008")
def test_lists_protected_files_changed_since_the_lock(repo):
    locked_feature_branch(repo)
    repo.commit({"tests/test_churn.py": "def test_churn():\n    assert True\n"}, "weaken")
    repo.commit({"tests/test_new.py": "def test_new():\n    assert 1\n"}, "a new test is fine")
    ev = lock_evidence(repo.root, "main", "feature/0042-churn")
    assert ev["signals"]["lock"]["changed_since"] == ["tests/test_churn.py"]


@pytest.mark.ac("0001/AC-008")
def test_no_lock_yet_is_not_measured(repo):
    locked_feature_branch(repo)
    repo.git("checkout", "-q", "test/0042-churn")
    ev = lock_evidence(repo.root, "main", "test/0042-churn")
    assert ev["status"] == "skipped"
    assert ev["reason"]
