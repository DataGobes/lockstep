"""Run with: python3 -m pytest plugins/lockstep-core/skills/lockstep/tests (from the Lockstep repo root)."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("next_step", HERE.parent / "scripts" / "next_step.py")
next_step = importlib.util.module_from_spec(spec)
sys.modules["next_step"] = next_step
spec.loader.exec_module(next_step)

STATUS = "status: {}\npii: {}\ntrack: data\njira: MXAAI-1\nlocked_at_commit: abc1234\n"


def git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", *args],
        check=True,
        capture_output=True,
    )


def write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def make_repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    shutil.copytree(
        LOCKSTEP / "core" / "src", tmp_path / ".lockstep" / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    write(
        tmp_path,
        {
            "specs/0001-done/status.yml": STATUS.format("implemented", "no"),
            "specs/0002-tests/status.yml": STATUS.format("approved", "no"),
            "specs/0003-build/status.yml": STATUS.format("tests-locked", "yes"),
        },
    )
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "specs")
    return tmp_path


def by_spec(root, base="main"):
    return {s.spec: s for s in next_step.steps(root, base)}


def test_next_step_follows_status_and_branches(tmp_path):
    root = make_repo(tmp_path)
    found = by_spec(root)
    assert found["0001"].skill is None
    assert found["0002"].skill == "tests-first" and "write the failing tests" in found["0002"].next
    assert found["0003"].skill == "implement" and "Copilot only" in found["0003"].next
    git(root, "branch", "test/0002-tests")
    git(root, "branch", "feature/0003-build")
    found = by_spec(root)
    assert "test PR is in progress" in found["0002"].next and found["0002"].branches == ["test/0002-tests"]
    assert found["0003"].skill == "self-review"


def test_merged_status_wins_over_the_working_tree(tmp_path):
    root = make_repo(tmp_path)
    write(root, {"specs/0002-tests/status.yml": STATUS.format("tests-locked", "no")})
    assert by_spec(root)["0002"].status == "approved"


def test_unmerged_spec_reads_the_working_tree(tmp_path):
    root = make_repo(tmp_path)
    git(root, "checkout", "-q", "-b", "spec/0004-new")
    write(root, {"specs/0004-new/status.yml": STATUS.format("draft", "no")})
    found = by_spec(root)
    assert found["0004"].skill == "spec"
    out = next_step.render(list(found.values()), "spec/0004-new")
    assert "On spec/0004-new: finish the spec" in out and "(/spec)" in out


def test_invalid_status_is_reported(tmp_path):
    root = make_repo(tmp_path)
    write(root, {"specs/0005-bad/status.yml": "status: nonsense\n"})
    assert by_spec(root)["0005"].status == "invalid"


def test_repo_without_lockstep(tmp_path, capsys):
    git(tmp_path, "init", "-q")
    assert next_step.main(["--root", str(tmp_path)]) == 1
    assert "/bootstrap-repo" in capsys.readouterr().out
