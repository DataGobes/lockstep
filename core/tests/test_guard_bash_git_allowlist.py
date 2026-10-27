"""Regression test for specs/bug-reports/guard-bash-git-allowlist.md: before a history rewrite, guard_bash trusts only
git subcommands that leave HEAD, branches and config alone, from a short positive list."""

from pathlib import Path

import pytest
from conftest import Repo

from lockstep_checks.hooks import Event, guard_bash


@pytest.fixture
def feature(tmp_path) -> Path:
    """The worktree `app-0042` on a feature branch, next to `app` on main."""
    (tmp_path / "app").mkdir()
    repo = Repo(tmp_path / "app")
    repo.commit({"a.txt": "a\n"})
    repo.commit({"a.txt": "b\n"})
    repo.git("worktree", "add", "-q", "-b", "feature/0042-x", str(tmp_path / "app-0042"))
    return tmp_path / "app-0042"


def bash(cmd: str, cwd: Path) -> Event:
    return Event({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})


@pytest.mark.parametrize(
    "cmd",
    [
        "git pull && git reset --hard HEAD~1",  # moves HEAD
        "git merge main && git rebase main",
        "git branch -f main HEAD && git reset --hard HEAD~1",  # moves a branch
        "git co main && git reset --hard HEAD~1",  # an alias can be anything
        "git $SUB main && git reset --hard HEAD~1",  # only the shell knows the subcommand
    ],
)
def test_other_git_subcommands_before_a_rewrite_are_not_trusted(feature, cmd):
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_read_only_git_before_a_rewrite_is_trusted(feature):
    cmd = "git fetch -q && git status && git diff --stat && git log -1 && git show -s && git add -A"
    d = guard_bash.hook(bash(cmd + " && git commit --amend --no-edit", feature))
    assert not d.block, d.message
