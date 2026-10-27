"""Regression test for specs/bug-reports/protect-tests-locked-at-commit.md: a test that existed at an implemented spec's
locked_at_commit stays locked when the base branch doesn't have it and no lock commit is found in first-parent history."""

import pytest

from lockstep_checks.hooks import Event, protect_tests


def status(state: str, sha: str) -> str:
    return f"status: {state}\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: {sha}\n"


def edit(root, rel: str) -> Event:
    return Event({"tool_name": "Edit", "tool_input": {"file_path": str(root / rel)}, "cwd": str(root)})


@pytest.fixture
def synced_repo(repo):
    """origin/main lacks tests/test_b.py; a mirror's implemented spec 0042 locked it; test/0042-churn-sync merges the
    mirror with --no-ff, so the lock sits on the merge's second parent."""
    repo.commit({"src/app.py": "x = 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("mirror")
    repo.commit({"tests/test_b.py": "def test_b():\n    assert 2 == 2\n", "specs/0042-churn/spec.md": "# spec\n"})
    lock = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"specs/0042-churn/status.yml": status("implemented", lock)})
    repo.git("checkout", "-q", "main")
    repo.branch("test/0042-churn-sync")
    repo.git("merge", "-q", "--no-ff", "-m", "sync", "mirror")
    return repo


def test_test_at_an_implemented_specs_locked_at_commit_is_locked(synced_repo):
    d = protect_tests.hook(edit(synced_repo.root, "tests/test_b.py"))
    assert d.block, d.warnings
    assert "tests/test_b.py existed before spec 0042 was tests-locked" in d.message


def test_tests_in_an_open_test_pr_stay_editable(repo):
    # The test PR's own second commit sets tests-locked with locked_at_commit at its first: still under review.
    repo.commit({"src/app.py": "x = 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("test/0042-churn")
    repo.commit({"tests/test_b.py": "def test_b():\n    assert 2 == 2\n", "specs/0042-churn/spec.md": "# spec\n"})
    first = repo.git("rev-parse", "HEAD").strip()
    repo.commit({"specs/0042-churn/status.yml": status("tests-locked", first)})
    assert not protect_tests.hook(edit(repo.root, "tests/test_b.py")).block
