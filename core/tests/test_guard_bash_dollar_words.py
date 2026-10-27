"""Regression test for specs/bug-reports/guard-bash-dollar-words.md: a word with a `$` in a git command before a history
rewrite isn't trusted, since only the shell knows what it becomes (`$'--upload-pack=...'`, `$OPT`)."""

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
        # bash decodes $'...' (ANSI-C quoting) to --upload-pack=...; shlex leaves a word starting with $.
        "git fetch $'--upload-pack=git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1",
        "git fetch $OPT . && git reset --hard HEAD~1",  # a variable can hold any option
        'git log $"--output=.git/HEAD" && git reset --hard HEAD~1',
    ],
)
def test_a_word_with_a_dollar_before_a_rewrite_is_not_trusted(feature, cmd):
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_a_dollar_in_the_rewrite_itself_is_still_allowed(feature):
    # The rewrite's own arguments don't move it: `-m "$MSG"` stays allowed on a feature branch.
    d = guard_bash.hook(bash('git add -A && git commit --amend -m "$MSG"', feature))
    assert not d.block, d.message
