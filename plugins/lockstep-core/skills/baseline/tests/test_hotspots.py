"""Run with: python3 -m pytest plugins/lockstep-core/skills/baseline/tests (from the Lockstep repo root)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hotspots", HERE.parent / "scripts" / "hotspots.py")
hotspots = importlib.util.module_from_spec(spec)
sys.modules["hotspots"] = hotspots
spec.loader.exec_module(hotspots)


def git(root, *args, author="t001"):
    env = {"GIT_AUTHOR_NAME": "Test Person", "GIT_AUTHOR_EMAIL": f"{author}@example.invalid", "HOME": str(root)}
    env |= {"GIT_COMMITTER_NAME": "Test Person", "GIT_COMMITTER_EMAIL": "t001@example.invalid"}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def commit(root, files, author="t001"):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "change", author=author)


def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, {"src/pricing/rules.py": "a = 1\n", "src/pricing/vat.py": "b = 1\n", "setup.py": "x\n"})
    commit(tmp_path, {"src/pricing/rules.py": "a = 2\n", "tests/test_rules.py": "t\n"}, author="t002")
    commit(tmp_path, {"src/pricing/rules.py": "a = 3\n", "docs/how.md": "d\n", "README.md": "r\n"})
    commit(tmp_path, {"src/orders/load.py": "c = 1\n", "src/pricing_v2/new.py": "n\n"})
    commit(tmp_path, {"specs/0001-orders/spec.md": "- In scope: `src/orders/load.py`\nsee src/pricing_v2\n"})
    return tmp_path


def by_path(found):
    return {a.path: a for a in found}


def test_ranks_areas_by_commits_and_ignores_tests_docs_and_specs(tmp_path):
    root = repo(tmp_path)
    rows = hotspots.changes(root, "main", "10 years ago")
    assert {p for _, _, p in rows} == {
        "src/pricing/rules.py",
        "src/pricing/vat.py",
        "setup.py",
        "src/orders/load.py",
        "src/pricing_v2/new.py",
    }
    found = hotspots.rank(rows, 2, hotspots.spec_text(root, "specs"), 10)
    assert found[0].path == "src/pricing"
    pricing = by_path(found)["src/pricing"]
    assert (pricing.commits, pricing.files, pricing.authors) == (3, 2, 2)
    assert by_path(found)["setup.py"].commits == 1


def test_pinned_means_a_spec_names_the_whole_path(tmp_path):
    root = repo(tmp_path)
    found = by_path(
        hotspots.rank(hotspots.changes(root, "main", "10 years ago"), 2, hotspots.spec_text(root, "specs"), 10)
    )
    assert found["src/orders"].pinned is True
    assert found["src/pricing_v2"].pinned is True
    assert found["src/pricing"].pinned is False


def test_depth_one_groups_by_top_folder(tmp_path):
    root = repo(tmp_path)
    found = hotspots.rank(hotspots.changes(root, "main", "10 years ago"), 1, "", 10)
    assert [a.path for a in found] == ["src", "setup.py"]


def test_cli_prints_json_and_fails_on_an_unknown_ref(tmp_path, capsys):
    root = repo(tmp_path)
    assert hotspots.main(["--root", str(root), "--ref", "main", "--since", "10 years ago", "--json", "--top", "1"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"path": "src/pricing", "commits": 3, "files": 2, "authors": 2, "pinned": False}
    ]
    assert hotspots.main(["--root", str(root), "--ref", "origin/main"]) == 1
    assert "is origin/main fetched?" in capsys.readouterr().err
