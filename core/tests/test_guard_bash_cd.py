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
