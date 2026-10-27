"""Regression test for specs/bug-reports/guard-bash-git-arguments.md: a trusted git subcommand is trusted only without
options that run commands or write files, and a history rewrite counts only as git's own subcommand."""

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
        # --upload-pack runs a command: here one that moves this worktree onto main before the reset.
        "git fetch --upload-pack='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1",
        "git fetch -u 'git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1",
        "git diff --output=.git/HEAD && git reset --hard HEAD~1",  # writes a file
        "git log --ext-diff -p && git reset --hard HEAD~1",  # runs the configured diff program
        "git show --textconv HEAD && git reset --hard HEAD~1",
    ],
)
def test_options_that_run_commands_or_write_are_not_trusted(feature, cmd):
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_a_rewrite_inside_another_git_commands_argument_is_blocked(feature):
    # The rewrite is the argument of a fetch, so the fetch's folder says nothing about where it runs.
    cmd = "git fetch --upload-pack='git -C ../app reset --hard HEAD~1' ."
    assert guard_bash.hook(bash(cmd, feature)).block


@pytest.mark.parametrize(
    "cmd",
    [
        # git takes any unambiguous prefix of a long option, and bundles short ones.
        "git fetch --upload-p='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1",
        "git fetch -qu 'git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1",
        "git diff --out=.git/HEAD && git reset --hard HEAD~1",
        "git log --ext -p && git reset --hard HEAD~1",
        # A refspec with a destination writes a branch; --update-head-ok lets it write the checked-out one.
        "git fetch --update-head-ok . main:feature/0042-x && git reset --hard HEAD~1",
    ],
)
def test_only_listed_options_are_trusted(feature, cmd):
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_listed_options_stay_trusted(feature):
    cmd = "git status -sb && git diff --cached --name-only && git log --oneline -5 && git fetch -q origin main"
    d = guard_bash.hook(bash(cmd + " && git commit --amend --no-edit", feature))
    assert not d.block, d.message
