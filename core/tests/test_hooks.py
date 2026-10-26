"""Hook tests: feed each hook the JSON payloads Claude Code and Copilot send (BUILD-010)."""

import json
import subprocess
from pathlib import Path

import pytest

from lockstep_checks.hooks import Event, guard_bash, protect_tests, run

SHIM = Path(__file__).resolve().parents[1] / "hooks" / "run-hook.sh"
LOCKED = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"


@pytest.fixture(autouse=True)
def no_pipeline_env(monkeypatch):
    for name in ("SYSTEM_PULLREQUEST_SOURCEBRANCH", "BUILD_SOURCEBRANCH", "SYSTEM_PULLREQUEST_TARGETBRANCH"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def locked_repo(repo):
    """main has tests/test_a.py; branch feature/0042-churn has a tests-locked spec."""
    repo.commit({"tests/test_a.py": "def test_a():\n    assert 1\n", "src/app.py": "x = 1\n"})
    repo.git("update-ref", "refs/remotes/origin/main", "main")
    repo.branch("feature/0042-churn")
    repo.commit({"specs/0042-churn/spec.md": "# spec\n", "specs/0042-churn/status.yml": LOCKED})
    return repo


def edit(root: Path, rel: str, tool="Edit", **extra) -> Event:
    return Event({"tool_name": tool, "tool_input": {"file_path": str(root / rel), **extra}, "cwd": str(root)})


# protect_tests


def test_blocks_edit_of_existing_test_when_locked(locked_repo):
    # BUILD-001
    d = protect_tests.hook(edit(locked_repo.root, "tests/test_a.py"))
    assert d.block
    assert "tests/test_a.py" in d.message and "stop and explain" in d.message


def test_allows_new_test_file_when_locked(locked_repo):
    # BUILD-002
    assert not protect_tests.hook(edit(locked_repo.root, "tests/test_new.py", tool="Write")).block


def test_allows_source_edit_when_locked(locked_repo):
    assert not protect_tests.hook(edit(locked_repo.root, "src/app.py")).block


def test_allows_test_edit_before_lock(locked_repo):
    status = LOCKED.replace("tests-locked", "approved").replace("locked_at_commit: abc1234\n", "")
    locked_repo.commit({"specs/0042-churn/status.yml": status})
    assert not protect_tests.hook(edit(locked_repo.root, "tests/test_a.py")).block


def test_branch_without_spec_allows_with_warning(locked_repo):
    locked_repo.git("checkout", "-q", "-b", "chore/tidy", "main")
    d = protect_tests.hook(edit(locked_repo.root, "tests/test_a.py"))
    assert not d.block and "no spec" in d.warnings[0]


def test_copilot_apply_patch_payload_is_checked(locked_repo):
    patch = "*** Begin Patch\n*** Update File: tests/test_a.py\n@@\n-    assert 1\n+    assert True\n*** End Patch\n"
    event = Event({"tool_name": "Edit", "tool_input": {"input": patch}, "cwd": str(locked_repo.root)})
    assert protect_tests.hook(event).block


def test_copilot_camelcase_payload_is_checked(locked_repo):
    args = json.dumps({"path": str(locked_repo.root / "tests/test_a.py")})
    event = Event({"toolName": "Edit", "toolArgs": args, "cwd": str(locked_repo.root)})
    assert protect_tests.hook(event).block


def test_relative_paths_resolve_against_cwd(locked_repo):
    event = Event({"tool_name": "Edit", "tool_input": {"file_path": "tests/test_a.py"}, "cwd": str(locked_repo.root)})
    assert protect_tests.hook(event).block


def test_other_tools_are_ignored(locked_repo):
    assert not protect_tests.hook(edit(locked_repo.root, "tests/test_a.py", tool="Read")).block


# guard_bash


def bash(cmd: str, cwd: Path | None = None, tool="Bash") -> Event:
    return Event({"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd or Path.cwd())})


@pytest.mark.parametrize(
    "cmd",
    [
        "databricks bundle deploy -t prod",
        "databricks bundle deploy --target=prod",
        "dbt build --target prod --select x",
        "cd x && dbt run -t 'production'",
        "git push --force origin feature/x",
        "git push -f",
        "git push --force-with-lease",
        "git push origin +feature/x",
        "git push origin --delete main",
        "uv run pytest -k 'not slow'",
        "pytest --deselect tests/test_a.py::test_a",
        "python -m pytest --ignore=tests/test_a.py",
    ],
)
def test_blocks_dangerous_commands(cmd):
    # BUILD-006
    d = guard_bash.hook(bash(cmd))
    assert d.block, cmd
    assert "BLOCKED by lockstep" in d.message


@pytest.mark.parametrize(
    "cmd",
    [
        "databricks bundle deploy -t dev",
        "dbt build --target ci --select state:modified+",
        "git push origin feature/0042-churn",
        "uv run pytest tests/test_a.py",
        "uv run pytest -x -q",
        "git log --format=%h -n 5",
        "echo production ready",
    ],
)
def test_allows_normal_commands(cmd):
    assert not guard_bash.hook(bash(cmd)).block, cmd


def test_powershell_tool_is_guarded():
    assert guard_bash.hook(bash("databricks bundle deploy -t prod", tool="PowerShell")).block


def test_history_rewrite_blocked_only_on_main(repo):
    repo.commit({"a.txt": "a\n"})
    assert guard_bash.hook(bash("git commit --amend -m x", repo.root)).block
    assert guard_bash.hook(bash("git reset --hard HEAD~1", repo.root)).block
    repo.branch("feature/0042-x")
    assert not guard_bash.hook(bash("git rebase -i main", repo.root)).block


# runner and shim


def test_runner_fails_closed_on_bad_input(capsys):
    assert run(guard_bash.hook, stdin="not json") == 2
    assert "blocking to be safe" in capsys.readouterr().err


def test_runner_exit_codes(capsys):
    assert run(guard_bash.hook, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})) == 0
    cmd = {"tool_name": "Bash", "tool_input": {"command": "git push -f"}}
    assert run(guard_bash.hook, stdin=json.dumps(cmd)) == 2
    assert "force-pushes" in capsys.readouterr().err


def shim(hook: str, payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SHIM), hook], input=json.dumps(payload), capture_output=True, text=True, cwd=cwd, check=False
    )


def test_shim_blocks_and_allows(locked_repo):
    root = locked_repo.root
    blocked = shim(
        "protect_tests", {"tool_name": "Edit", "tool_input": {"file_path": "tests/test_a.py"}, "cwd": str(root)}, root
    )
    assert blocked.returncode == 2 and "BLOCKED by lockstep" in blocked.stderr
    allowed = shim("guard_bash", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(root)}, root)
    assert allowed.returncode == 0, allowed.stderr


def test_shim_rejects_unknown_hook(tmp_path):
    assert shim("rm_rf", {}, tmp_path).returncode == 2
