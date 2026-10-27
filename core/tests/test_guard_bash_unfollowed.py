"""Regression test for specs/bug-reports/guard-bash-unfollowed.md: a history rewrite whose checkout guard_bash can't
work out is blocked from any branch, not only when the session itself is on main."""

from pathlib import Path

import pytest
from conftest import Repo

from lockstep_checks.hooks import Event, guard_bash


@pytest.fixture
def checkouts(tmp_path) -> tuple[Path, Path]:
    """`app` on main and the worktree `app-0042` next to it on a feature branch."""
    (tmp_path / "app").mkdir()
    repo = Repo(tmp_path / "app")
    repo.commit({"a.txt": "a\n"})
    repo.commit({"a.txt": "b\n"})
    repo.git("worktree", "add", "-q", "-b", "feature/0042-x", str(tmp_path / "app-0042"))
    return repo.root, tmp_path / "app-0042"


def bash(cmd: str, cwd: Path) -> Event:
    return Event({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})


@pytest.mark.parametrize(
    "cmd",
    [
        "cd -P ../app && git reset --hard HEAD~1",  # a cd with options
        "cd $APP && git reset --hard HEAD~1",  # a folder only the shell knows
        "cd ~/app && git reset --hard HEAD~1",  # ~ follows the shell's $HOME
        "(cd ../app && git reset --hard HEAD~1)",
        "if true; then cd ../app; fi && git reset --hard HEAD~1",  # a cd inside shell syntax
        "command cd ../app && git reset --hard HEAD~1",
        "eval 'cd ../app' && git reset --hard HEAD~1",
        "source ./go.sh && git reset --hard HEAD~1",
        "git -c core.worktree=../app reset --hard HEAD~1",  # config can point git at another checkout
        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.worktree GIT_CONFIG_VALUE_0=../app; git reset --hard HEAD~1",
        "bash -c 'git -C ../app reset --hard HEAD~1'",  # git run by another command
    ],
)
def test_a_rewrite_whose_checkout_it_cannot_work_out_is_blocked_from_a_feature_branch(checkouts, cmd):
    _, feature = checkouts
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_cd_with_cdpath_set_is_not_followed(checkouts, monkeypatch):
    # bash searches $CDPATH before the current folder for a bare name: `cd app` lands in the main checkout.
    main, feature = checkouts
    (feature / "app").mkdir()
    monkeypatch.setenv("CDPATH", str(main.parent))
    assert guard_bash.hook(bash("cd app && git reset --hard HEAD~1", feature)).block


def test_cd_resolves_dot_dot_before_symlinks_like_the_shell(checkouts):
    # The shell's cd takes `link/..` as the folder holding the link (the main checkout), not the link target's parent.
    main, feature = checkouts
    (feature / "sub").mkdir()
    (main / "link").symlink_to(feature / "sub")
    assert guard_bash.hook(bash("cd ../app/link/.. && git reset --hard HEAD~1", feature)).block


def test_a_plain_rewrite_on_a_feature_branch_is_still_allowed(checkouts):
    _, feature = checkouts
    d = guard_bash.hook(bash("git rebase -i HEAD~1 && git commit --amend -m x", feature))
    assert not d.block, d.message


@pytest.mark.parametrize(
    "cmd",
    [
        "cd ../app; true # && cd ../app-0042\ngit reset --hard HEAD~1",  # the second cd is a comment
        "shopt -s autocd; ../app; git reset --hard HEAD~1",  # a folder name alone changes into it
        "d=../app; read -r d <<< ../app; cd $d && git reset --hard HEAD~1",
        "git config core.worktree ../app && git reset --hard HEAD~1",  # git config outlives its command
        "git checkout main && git reset --hard HEAD~1",  # the branch changes before the rewrite
        "ruff format . && git commit --amend --no-edit",  # any other command first: not followed, by design
    ],
)
def test_only_cd_and_plain_git_before_a_rewrite_are_trusted(checkouts, cmd):
    # An allowlist, not a denylist: before a history rewrite, only `cd <folder>` and git commands that don't move
    # HEAD or change config are followed. Run the rewrite as its own command instead.
    _, feature = checkouts
    assert guard_bash.hook(bash(cmd, feature)).block, cmd


def test_plain_git_before_a_rewrite_is_trusted(checkouts):
    _, feature = checkouts
    d = guard_bash.hook(bash("git add -A && git status --short && git commit --amend --no-edit", feature))
    assert not d.block, d.message
