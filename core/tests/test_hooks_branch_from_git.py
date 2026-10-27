"""Regression test for specs/bug-reports/hooks-branch-from-git.md: the hooks judge the branch git has checked out, not
the PR branch a CI job's variables name, so an agent running inside CI gets the same protection as on a laptop."""

import pytest

from lockstep_checks.hooks import Event, guard_bash, protect_tests

LOCKED = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"
CI_SAYS_FEATURE = [
    {"GITHUB_ACTIONS": "true", "GITHUB_HEAD_REF": "feature/0099-other"},
    {"TF_BUILD": "True", "SYSTEM_PULLREQUEST_SOURCEBRANCH": "refs/heads/feature/0099-other"},
]


@pytest.mark.parametrize("ci_env", CI_SAYS_FEATURE)
def test_guard_bash_blocks_a_rewrite_of_a_main_checkout_whatever_ci_says(repo, monkeypatch, ci_env):
    repo.commit({"a.txt": "a\n"})
    repo.commit({"a.txt": "b\n"})
    for name, value in ci_env.items():
        monkeypatch.setenv(name, value)
    cmd = Event({"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}, "cwd": str(repo.root)})
    assert guard_bash.hook(cmd).block


@pytest.mark.parametrize("ci_env", CI_SAYS_FEATURE)
def test_protect_tests_judges_the_checked_out_spec_whatever_ci_says(repo, monkeypatch, ci_env):
    repo.commit({"tests/test_a.py": "def test_a():\n    assert 1 == 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("feature/0042-churn")
    repo.commit({"specs/0042-churn/spec.md": "# spec\n", "specs/0042-churn/status.yml": LOCKED})
    for name, value in ci_env.items():
        monkeypatch.setenv(name, value)
    edit = Event(
        {"tool_name": "Edit", "tool_input": {"file_path": str(repo.root / "tests/test_a.py")}, "cwd": str(repo.root)}
    )
    d = protect_tests.hook(edit)
    assert d.block, d.warnings
