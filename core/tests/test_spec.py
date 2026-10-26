import json
import subprocess
import sys
from pathlib import Path

import pytest

from lockstep_checks.config import load_config
from lockstep_checks.spec import SpecError, current_branch, resolve_spec

SRC = Path(__file__).resolve().parents[1] / "src"
LOCKED = "status: tests-locked\npii: no\ntrack: data\njira: MXAAI-42\nlocked_at_commit: abc1234\n"


def make_spec(root: Path, name: str, status: str | None = LOCKED) -> Path:
    d = root / "specs" / name
    d.mkdir(parents=True)
    (d / "spec.md").write_text("# spec\n", encoding="utf-8")
    if status is not None:
        (d / "status.yml").write_text(status, encoding="utf-8")
    return d


@pytest.fixture
def cfg(tmp_path):
    return load_config(tmp_path)


def test_resolves_spec_from_branch(tmp_path, cfg):
    d = make_spec(tmp_path, "0042-churn-features")
    r = resolve_spec(tmp_path, "feature/0042-churn-features", cfg)
    assert r.state == "found"
    assert r.spec_id == "0042"
    assert r.spec_dir == d
    assert r.status.tests_locked


def test_slug_may_differ_from_branch(tmp_path, cfg):
    make_spec(tmp_path, "0042-churn-features")
    assert resolve_spec(tmp_path, "test/0042-red-tests", cfg).state == "found"


def test_branch_without_spec_id(tmp_path, cfg):
    r = resolve_spec(tmp_path, "main", cfg)
    assert r.state == "no-match"
    assert r.spec_id is None


def test_spec_id_without_folder(tmp_path, cfg):
    make_spec(tmp_path, "0041-other")
    r = resolve_spec(tmp_path, "feature/0042-churn", cfg)
    assert r.state == "missing"
    assert r.spec_id == "0042"


def test_id_prefix_does_not_match_longer_id(tmp_path, cfg):
    make_spec(tmp_path, "00420-other")
    assert resolve_spec(tmp_path, "feature/0042-churn", cfg).state == "missing"


def test_two_folders_for_one_id_is_an_error(tmp_path, cfg):
    make_spec(tmp_path, "0042-a")
    make_spec(tmp_path, "0042-b")
    with pytest.raises(SpecError, match="0042-a.*0042-b"):
        resolve_spec(tmp_path, "feature/0042-a", cfg)


def test_missing_status_file_is_an_error(tmp_path, cfg):
    make_spec(tmp_path, "0042-churn", status=None)
    with pytest.raises(SpecError, match="status.yml"):
        resolve_spec(tmp_path, "feature/0042-churn", cfg)


def test_invalid_status_file_names_the_file(tmp_path, cfg):
    make_spec(tmp_path, "0042-churn", status="status: nope\npii: no\ntrack: data\n")
    with pytest.raises(SpecError, match=r"0042-churn[/\\]status.yml"):
        resolve_spec(tmp_path, "feature/0042-churn", cfg)


def test_template_folder_is_never_a_spec(tmp_path, cfg):
    make_spec(tmp_path, "_template")
    assert resolve_spec(tmp_path, "feature/_template", cfg).state == "no-match"


@pytest.mark.parametrize(
    "env, expected",
    [
        (
            {"SYSTEM_PULLREQUEST_SOURCEBRANCH": "refs/heads/feature/0042-x", "BUILD_SOURCEBRANCH": "refs/pull/7/merge"},
            "feature/0042-x",
        ),
        ({"BUILD_SOURCEBRANCH": "refs/heads/feature/0043-y"}, "feature/0043-y"),
    ],
)
def test_branch_from_azure_pipelines_env(tmp_path, env, expected):
    assert current_branch(tmp_path, env) == expected


def test_branch_from_git(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "feature/0044-z", str(tmp_path)], check=True)
    assert current_branch(tmp_path, {}) == "feature/0044-z"


def test_detached_head_without_env_gives_none(tmp_path):
    assert current_branch(tmp_path, {}) is None  # not a git repo at all


def run_cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "lockstep_checks.spec", "--root", str(tmp_path), *args],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(SRC), "PATH": ""},
    )


def test_cli_prints_json(tmp_path):
    make_spec(tmp_path, "0042-churn")
    p = run_cli(tmp_path, "--branch", "feature/0042-churn")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["state"] == "found"
    assert out["status"]["status"] == "tests-locked"
    assert out["status"]["tests_locked"] is True


def test_cli_fails_loudly_on_bad_spec(tmp_path):
    make_spec(tmp_path, "0042-churn", status="status: nope\n")
    p = run_cli(tmp_path, "--branch", "feature/0042-churn")
    assert p.returncode == 1
    assert "status.yml" in p.stderr
