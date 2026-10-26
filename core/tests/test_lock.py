"""Red tests stay off main: the test PR merges into the feature branch, and the lock starts there."""

import json

import pytest

from lockstep_checks.check_test_tamper import _run
from lockstep_checks.cli import run
from lockstep_checks.config import load_config
from lockstep_checks.hooks import protect_tests
from lockstep_checks.hooks import run as run_hook
from lockstep_checks.lock import branch_tip, lock_commit
from lockstep_checks.spec import resolve_spec

APPROVED = "status: approved\npii: no\ntrack: data\njira: MXAAI-42\n"
LOCKED = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"
RED = "from app import churn\n\ndef test_churn():\n    assert churn() == 3\n"


@pytest.fixture(autouse=True)
def no_pipeline_env(monkeypatch):
    for name in ("SYSTEM_PULLREQUEST_SOURCEBRANCH", "BUILD_SOURCEBRANCH", "SYSTEM_PULLREQUEST_TARGETBRANCH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SYSTEM_PULLREQUEST_SOURCECOMMITID", raising=False)


def stacked(repo, squash=False, merge=True):
    """main has an approved spec; the test PR adds red tests and the lock, gets a review fix, merges into feature."""
    repo.commit(
        {"src/app.py": "def churn():\n    raise NotImplementedError\n", "specs/0042-churn/status.yml": APPROVED}
    )
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("feature/0042-churn")
    repo.branch("test/0042-churn")
    repo.commit({"tests/test_churn.py": RED}, "MXAAI-42 Add failing tests for spec 0042")
    repo.commit({"specs/0042-churn/status.yml": LOCKED}, "MXAAI-42 Lock tests")
    repo.commit({"tests/test_churn.py": RED + "\ndef test_empty():\n    assert churn() == 0\n"}, "review fix")
    if not merge:
        return repo
    repo.git("checkout", "-q", "feature/0042-churn")
    if squash:
        repo.git("merge", "-q", "--squash", "test/0042-churn")
        repo.git("commit", "-q", "-m", "Merged PR 7: tests for 0042")
    else:
        repo.git("merge", "-q", "--no-ff", "-m", "Merged PR 7: tests for 0042", "test/0042-churn")
    return repo


def lock_of(repo, branch):
    cfg = load_config(repo.root)
    return lock_commit(repo.root, "main", resolve_spec(repo.root, branch, cfg), cfg)


@pytest.mark.parametrize("squash", [False, True])
def test_lock_is_where_the_test_pr_merged(repo, squash):
    stacked(repo, squash)
    assert lock_of(repo, "feature/0042-churn") == repo.git("rev-parse", "HEAD").strip()


def test_no_lock_on_the_test_branch(repo):
    stacked(repo, merge=False)
    assert lock_of(repo, "test/0042-churn") is None


def tamper(repo, base="main"):
    return run("check_test_tamper", "", _run, ["--root", str(repo.root), "--base", base, "--title", "MXAAI-42 x"])


@pytest.mark.parametrize("squash", [False, True])
def test_feature_pr_fails_when_a_locked_test_changes(repo, capsys, squash):
    stacked(repo, squash)
    assert tamper(repo) == 0, capsys.readouterr().out  # the review fix in the test PR is fine
    repo.commit({"tests/test_churn.py": "def test_churn():\n    assert True\n"})
    assert tamper(repo) == 1
    assert "tests/test_churn.py: modifies a locked test" in capsys.readouterr().out


def test_feature_pr_may_add_tests_and_code(repo, capsys):
    stacked(repo)
    repo.commit({"src/app.py": "def churn():\n    return 3\n", "tests/test_unit.py": "def test_u():\n    assert 1\n"})
    assert tamper(repo) == 0, capsys.readouterr().out


def test_test_pr_may_still_change_its_own_tests(repo, capsys):
    stacked(repo, merge=False)
    repo.commit({"tests/test_churn.py": RED.replace("== 3", "== 4")}, "second review fix")
    assert tamper(repo, base="feature/0042-churn") == 0, capsys.readouterr().out


def test_pipeline_judges_the_pr_branch_not_the_merge_with_main(repo, capsys, monkeypatch):
    stacked(repo)
    repo.commit({"tests/test_churn.py": "def test_churn():\n    assert True\n"})
    tip = repo.git("rev-parse", "HEAD").strip()
    monkeypatch.setenv("SYSTEM_PULLREQUEST_SOURCECOMMITID", tip)
    assert branch_tip() == tip
    repo.git("checkout", "-q", "--detach", "main")  # stand-in for the PR merge commit
    repo.git("merge", "-q", "--no-ff", "-m", "Merge PR into main", tip)
    monkeypatch.setenv("SYSTEM_PULLREQUEST_SOURCEBRANCH", "refs/heads/feature/0042-churn")
    assert tamper(repo) == 1
    assert "modifies a locked test" in capsys.readouterr().out


def edit(root, rel):
    return json.dumps({"tool_name": "Edit", "tool_input": {"file_path": rel}, "cwd": str(root)})


def test_hook_blocks_locked_test_on_the_feature_branch(repo):
    stacked(repo)
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_churn.py")) == 2
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_new.py")) == 0


def test_hook_allows_review_fixes_on_the_test_branch(repo):
    stacked(repo, merge=False)
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_churn.py")) == 0


def test_parallel_stream_branch_keeps_the_lock(repo):
    # A stream of the implement skill's parallel mode branches from the feature branch: same spec, same lock.
    stacked(repo)
    lock = repo.git("rev-parse", "HEAD").strip()
    repo.branch("feature/0042-churn--storage")
    repo.commit({"src/storage.py": "x = 1\n"})
    assert lock_of(repo, "feature/0042-churn--storage") == lock
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_churn.py")) == 2
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_storage_unit.py")) == 0


def test_stream_pr_into_the_feature_branch_fails_when_a_locked_test_changes(repo, capsys):
    stacked(repo)
    repo.branch("feature/0042-churn--storage")
    repo.commit({"src/storage.py": "x = 1\n", "tests/test_storage.py": "def test_s():\n    assert 1\n"})
    assert tamper(repo, base="feature/0042-churn") == 0, capsys.readouterr().out
    repo.commit({"tests/test_churn.py": "def test_churn():\n    assert True\n"})
    assert tamper(repo, base="feature/0042-churn") == 1
    assert "tests/test_churn.py" in capsys.readouterr().out


def merge_main_into_feature(repo):
    """Main moves on (another spec merged) and the feature branch takes it in, as teams do before their PR."""
    repo.git("checkout", "-q", "main")
    repo.commit({"src/other.py": "y = 2\n"}, "another spec merged")
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.git("checkout", "-q", "feature/0042-churn")
    repo.git("merge", "-q", "--no-ff", "-m", "Merge main", "main")


@pytest.mark.parametrize("squash", [False, True])
def test_lock_survives_merging_main_into_the_feature_branch(repo, squash):
    stacked(repo, squash)
    lock = repo.git("rev-parse", "HEAD").strip()
    merge_main_into_feature(repo)
    assert lock_of(repo, "feature/0042-churn") == lock


def test_locked_tests_stay_locked_after_merging_main(repo, capsys):
    stacked(repo)
    merge_main_into_feature(repo)
    assert run_hook(protect_tests.hook, stdin=edit(repo.root, "tests/test_churn.py")) == 2
    repo.commit({"tests/test_churn.py": "def test_churn():\n    assert True\n"})
    assert tamper(repo) == 1
    assert "tests/test_churn.py: modifies a locked test" in capsys.readouterr().out


def test_hook_guards_the_implement_worktree_from_the_main_checkout(repo, tmp_path_factory):
    # start_implement puts the feature branch in ../<repo>-<id>; Claude Code's cwd stays in the main checkout.
    stacked(repo)
    repo.git("checkout", "-q", "main")
    worktree = tmp_path_factory.mktemp("wt") / "app-0042"
    repo.git("worktree", "add", "-q", str(worktree), "feature/0042-churn")
    event = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(worktree / "tests/test_churn.py")}, "cwd": str(repo.root)}
    )
    assert run_hook(protect_tests.hook, stdin=event) == 2
    new = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(worktree / "tests/x/test_new.py")},
            "cwd": str(repo.root),
        }
    )
    assert run_hook(protect_tests.hook, stdin=new) == 0
