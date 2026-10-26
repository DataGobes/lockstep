"""Run with: python3 -m pytest plugins/lockstep-core/skills/implement/tests (from the Lockstep repo root)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("streams", HERE.parent / "scripts" / "streams.py")
streams = importlib.util.module_from_spec(spec)
sys.modules["streams"] = streams
spec.loader.exec_module(streams)

FEATURE = "feature/0042-churn"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def commit(root, files, message="x"):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", "commit", "-qm", message)


@pytest.fixture
def feature(tmp_path):
    """A feature worktree, as start_implement.py leaves it: repo/ on main, repo-0042/ on the feature branch."""
    main = tmp_path / "repo"
    git(tmp_path, "init", "-q", "-b", "main", str(main))
    commit(main, {"src/core.py": "CONTRACT = 1\n"})
    git(main, "branch", FEATURE)
    wt = tmp_path / "repo-0042"
    git(main, "worktree", "add", "-q", str(wt), FEATURE)
    return wt


def test_add_creates_a_worktree_and_branch_per_stream(feature):
    created = streams.add(feature, ["storage", "api"])
    assert [c["branch"] for c in created] == [f"{FEATURE}--storage", f"{FEATURE}--api"]
    for c in created:
        path = Path(c["worktree"])
        assert path == feature.parent / f"repo-0042--{c['stream']}"
        assert (path / "src/core.py").read_text() == "CONTRACT = 1\n"
        assert git(path, "symbolic-ref", "--short", "HEAD").strip() == c["branch"]


def test_stream_branch_still_names_the_spec(feature):
    # The default branch_pattern in lockstep.toml must resolve a stream to the same spec.
    import re

    pattern = re.compile(r"^(?:feature|bugfix|hotfix|test|spec)/(?P<id>\d{4})-")
    assert pattern.match(f"{FEATURE}--storage")["id"] == "0042"


@pytest.mark.parametrize("names", [["Storage"], ["a_b"], ["x", "x"]])
def test_bad_names_are_refused(feature, names):
    with pytest.raises(streams.StreamError, match="stream names"):
        streams.add(feature, names)


def test_only_from_a_clean_feature_worktree(feature):
    with pytest.raises(streams.StreamError, match="feature worktree"):
        streams.add(feature.parent / "repo", ["storage"])
    (feature / "src/shared.py").write_text("x\n")
    with pytest.raises(streams.StreamError, match="commit the shared contracts first"):
        streams.add(feature, ["storage"])


def test_a_stream_cannot_be_added_twice(feature):
    streams.add(feature, ["storage"])
    with pytest.raises(streams.StreamError, match="already exists"):
        streams.add(feature, ["storage"])


def test_remove_refuses_unmerged_work_then_cleans_up_after_merge(feature):
    [s] = streams.add(feature, ["storage"])
    wt = Path(s["worktree"])
    commit(wt, {"src/storage.py": "def save(): ...\n"})
    assert streams.list_streams(feature)[0]["unmerged_commits"] == 1
    with pytest.raises(streams.StreamError, match="not on feature/0042-churn yet"):
        streams.remove(feature, "storage")
    git(feature, "merge", "-q", "--ff-only", s["branch"])
    assert streams.remove(feature, "storage")["removed"] is True
    assert not wt.exists()
    assert streams.list_streams(feature) == []


def test_squash_merged_stream_counts_as_merged(feature):
    [a, b] = streams.add(feature, ["storage", "api"])
    commit(Path(a["worktree"]), {"src/storage.py": "def save(): ...\n"})
    commit(Path(b["worktree"]), {"src/api.py": "def get(): ...\n"})
    # api's PR merged first, then storage's as a squash, as Azure DevOps does.
    git(feature, "merge", "-q", "--no-edit", b["branch"])
    git(feature, "merge", "-q", "--squash", a["branch"])
    git(feature, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", "commit", "-qm", "squash")
    assert streams.remove(feature, "storage")["removed"] is True
    assert streams.remove(feature, "api")["removed"] is True


def test_cli_prints_json(feature, capsys):
    assert streams.main(["add", "storage", "--root", str(feature)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["stream"] == "storage"
    assert streams.main(["remove", "nope", "--root", str(feature)]) == 1
    assert "no stream branch" in capsys.readouterr().err
