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


def test_feature_branch_status_wins_once_the_test_pr_merged_there(tmp_path):
    # Red tests stay off main: main says approved, the feature branch has the lock.
    root = make_repo(tmp_path)
    git(root, "checkout", "-q", "-b", "feature/0002-tests")
    write(root, {"specs/0002-tests/status.yml": STATUS.format("tests-locked", "no")})
    git(root, "commit", "-qam", "Merged PR 7: tests for 0002")
    git(root, "checkout", "-q", "main")
    step = by_spec(root)["0002"]
    assert (step.status, step.skill) == ("tests-locked", "implement")
    git(root, "checkout", "-q", "feature/0002-tests")
    write(root, {"src/churn.py": "x = 1\n"})
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first slice")
    assert by_spec(root)["0002"].skill == "self-review"


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


def test_baseline_spec_routes_to_the_baseline_skill(tmp_path):
    root = make_repo(tmp_path)
    write(
        root,
        {"specs/0004-pricing/status.yml": "status: approved\npii: no\ntrack: data\njira: MXAAI-4\nkind: baseline\n"},
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "baseline spec")
    step = by_spec(root)["0004"]
    assert step.skill == "baseline" and "passing tests" in step.next
    git(root, "branch", "baseline/0004-pricing")
    step = by_spec(root)["0004"]
    assert step.branches == ["baseline/0004-pricing"] and "baseline in progress" in step.next


def test_quick_lane_test_pr_is_not_reported_as_implementation(tmp_path):
    # The spec and its tests are on the test branch; the feature branch has neither until the test PR merges.
    root = make_repo(tmp_path)
    git(root, "branch", "feature/0004-quick")
    git(root, "checkout", "-q", "-b", "test/0004-quick")
    write(root, {"specs/0004-quick/status.yml": STATUS.format("tests-locked", "no")})
    git(root, "add", "-A")
    git(root, "commit", "-qm", "spec and failing tests")
    step = by_spec(root)["0004"]
    assert step.status == "tests-locked"
    assert step.skill == "tests-first" and "test PR is in progress" in step.next


def test_locked_spec_without_a_feature_branch_mentions_marking_it_implemented(tmp_path):
    step = by_spec(make_repo(tmp_path))["0003"]
    assert step.skill == "implement" and "set status: implemented" in step.next
