"""Run with: python3 -m pytest plugins/lockstep-core/skills/implement/tests (from the Lockstep repo root)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("start_implement", HERE.parent / "scripts" / "start_implement.py")
start_implement = importlib.util.module_from_spec(spec)
sys.modules["start_implement"] = start_implement
spec.loader.exec_module(start_implement)

LOCKED = "status: tests-locked   # x\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", "commit", "-qm", "x")


@pytest.fixture
def clone(tmp_path):
    """A clone of a remote whose main has spec 0042 with the given status."""

    def make(status: str = LOCKED) -> Path:
        seed = tmp_path / "seed"
        git(tmp_path, "init", "-q", "-b", "main", str(seed))
        commit(seed, {"specs/0042-churn/spec.md": "# s\n", "specs/0042-churn/status.yml": status})
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(tmp_path / "remote")], check=True)
        work = tmp_path / "work" / "repo"
        subprocess.run(["git", "clone", "-q", str(tmp_path / "remote"), str(work)], check=True)
        return work

    return make


def test_creates_worktree_and_branch(clone):
    repo = clone()
    out = start_implement.start(repo, "0042")
    assert out["branch"] == "feature/0042-churn"
    worktree = Path(out["worktree"])
    assert worktree == repo.parent / "repo-0042"
    assert (worktree / "specs" / "0042-churn" / "status.yml").is_file()
    head = subprocess.run(
        ["git", "-C", str(worktree), "branch", "--show-current"], check=True, capture_output=True, text=True
    )
    assert head.stdout.strip() == "feature/0042-churn"


def test_second_implementation_is_refused(clone):
    repo = clone()
    start_implement.start(repo, "0042")
    with pytest.raises(start_implement.NotReady, match="already has implementation work"):
        start_implement.start(repo, "0042")


@pytest.mark.parametrize(
    "status, fragment",
    [
        ("status: approved\npii: no\ntrack: data\njira: MXAAI-42\n", "test PR must merge first"),
        (LOCKED.replace("pii: no", "pii: yes"), "Copilot"),
        (LOCKED.replace("tests-locked", "implemented"), "already implemented"),
    ],
)
def test_spec_not_ready(clone, status, fragment):
    with pytest.raises(start_implement.NotReady, match=fragment):
        start_implement.start(clone(status), "0042", dry_run=True)


def test_spec_only_on_a_local_branch_is_not_enough(clone):
    with pytest.raises(start_implement.NotReady, match="not on origin/main"):
        start_implement.start(clone(), "0043", dry_run=True)


def test_dry_run_creates_nothing(clone):
    repo = clone()
    out = start_implement.start(repo, "0042", dry_run=True)
    assert not Path(out["worktree"]).exists()
