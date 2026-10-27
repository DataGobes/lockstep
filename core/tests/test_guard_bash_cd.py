"""Regression test for specs/bug-reports/guard-bash-cd.md: the "rewrites history on main" rule judges the checkout the
git command runs in, after a `cd` or `git -C`, not the session's own folder."""

from pathlib import Path

import pytest
from conftest import Repo

from lockstep_checks.hooks import Event, guard_bash


@pytest.fixture
def checkouts(tmp_path) -> tuple[Path, Path]:
    """A checkout on main and a worktree next to it on a feature branch."""
    (tmp_path / "app").mkdir()
    repo = Repo(tmp_path / "app")
    repo.commit({"a.txt": "a\n"})
    repo.commit({"a.txt": "b\n"})
    repo.git("worktree", "add", "-q", "-b", "feature/0042-x", str(tmp_path / "app-0042"))
    return repo.root, tmp_path / "app-0042"


def bash(cmd: str, cwd: Path) -> Event:
    return Event({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})


def test_cd_into_a_feature_worktree_allows_amend(checkouts):
    main, _ = checkouts
    d = guard_bash.hook(bash("cd ../app-0042 && git commit --amend -m x", main))
    assert not d.block, d.message


def test_cd_into_main_blocks_reset(checkouts):
    _, feature = checkouts
    assert guard_bash.hook(bash("cd ../app && git reset --hard HEAD~1", feature)).block


def test_git_dash_c_into_main_blocks_rebase(checkouts):
    main, feature = checkouts
    assert guard_bash.hook(bash(f"git -C {main} rebase HEAD~1", feature)).block


def test_git_dash_c_into_a_feature_worktree_allows_amend(checkouts):
    main, _ = checkouts
    d = guard_bash.hook(bash("git -C ../app-0042 commit --amend -m x", main))
    assert not d.block, d.message


@pytest.mark.parametrize(
    "cmd",
    [
        "(cd ../app-0042 && git log); git reset --hard HEAD~1",  # the cd stays in the subshell
        "cd ../app-0042 | git reset --hard HEAD~1",  # each side of a pipe is its own subshell
        "cd ../app-0042 || git reset --hard HEAD~1",  # the reset runs only if the cd failed
        "cd ../app-0042 && cd $(echo ..)/app && git reset --hard HEAD~1",
        "pushd ../app-0042 && popd && git reset --hard HEAD~1",
        "cd ../app-0042 && git --git-dir=../app/.git reset --hard HEAD~1",
        "cd ../app-0042 && GIT_DIR=../app/.git git reset --hard HEAD~1",
        "git -C ../app-0042 -C ../app reset --hard HEAD~1",
    ],
)
def test_a_folder_change_it_cannot_follow_still_checks_the_session_folder(checkouts, cmd):
    main, _ = checkouts
    assert guard_bash.hook(bash(cmd, main)).block, cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "cd -P ../app && git reset --hard HEAD~1",  # a cd with options
        "cd $APP && git reset --hard HEAD~1",  # a folder only the shell knows
        "(cd ../app && git reset --hard HEAD~1)",
        "git -c core.worktree=../app reset --hard HEAD~1",  # config can point git at another checkout
        "bash -c 'git -C ../app reset --hard HEAD~1'",  # git run by another command
        "xargs git -C ../app reset --hard HEAD~1 < /dev/null",
    ],
)
def test_a_rewrite_whose_folder_it_cannot_follow_is_blocked_from_any_branch(checkouts, cmd):
    # From a feature worktree: checking the session's folder isn't enough, since that folder isn't on main.
    _, feature = checkouts
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_a_plain_rewrite_on_a_feature_branch_is_still_allowed(checkouts):
    _, feature = checkouts
    d = guard_bash.hook(bash("git rebase -i HEAD~1 && git commit --amend -m x", feature))
    assert not d.block, d.message
