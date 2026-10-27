"""Regression test for specs/bug-reports/guard-bash-git-options.md: a read-only git command before a history rewrite
stays trusted only with options from a short list, so abbreviations and bundles of other options don't get through."""

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
