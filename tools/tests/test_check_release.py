"""Run with: python3 -m pytest tools/tests (from the Lockstep repo root)."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[1]
spec = importlib.util.spec_from_file_location("check_release", HERE.parent / "check_release.py")
check_release = importlib.util.module_from_spec(spec)
sys.modules["check_release"] = check_release
spec.loader.exec_module(check_release)


# The released version, read from the repo so these tests survive a release.
CURRENT = json.loads((LOCKSTEP / "plugins" / "lockstep-core" / ".claude-plugin" / "plugin.json").read_text())["version"]


@pytest.fixture
def repo(tmp_path):
    for rel in ("plugins", "docs", ".claude-plugin", "core", "templates"):
        shutil.copytree(LOCKSTEP / rel, tmp_path / rel, ignore=shutil.ignore_patterns("__pycache__", ".venv"))
    shutil.copy(LOCKSTEP / "README.md", tmp_path / "README.md")
    return tmp_path


def test_this_repo_is_consistent(repo):
    assert check_release.check(repo) == []


def test_version_mismatch_and_missing_docs_are_reported(repo):
    manifest = repo / "plugins" / "lockstep-ai" / ".claude-plugin" / "plugin.json"
    manifest.write_text(manifest.read_text().replace(f'"version": "{CURRENT}"', '"version": "9.9.9"'))
    (repo / "docs" / "skills" / "spec.md").unlink()
    readme = repo / "README.md"
    readme.write_text(readme.read_text().replace("(plugins/lockstep-data/skills/dbt-impact/SKILL.md)", "(x)"))
    problems = check_release.check(repo)
    assert any(f"lockstep-ai: version 9.9.9 in plugin.json, {CURRENT}" in p for p in problems)
    assert any("no page docs/skills/spec.md" in p for p in problems)
    assert any("dbt-impact/SKILL.md: not linked from README.md" in p for p in problems)


def test_set_version_updates_every_lockstep_plugin(repo):
    check_release.set_version(repo, "9.0.0", None)
    market = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text())
    versions = {p["name"]: p["version"] for p in market["plugins"]}
    assert market["metadata"]["version"] == "9.0.0"
    assert all(v == "9.0.0" for n, v in versions.items() if n.startswith("lockstep-"))
    assert 'version = "9.0.0"' in (repo / "core" / "pyproject.toml").read_text()
    assert '__version__ = "9.0.0"' in (repo / "core/src/lockstep_checks/__init__.py").read_text()
    assert 'core_version = "9.0"' in (repo / "templates" / "lockstep.toml").read_text()
    assert check_release.check(repo) == []


def test_stale_core_version_is_reported(repo):
    init = repo / "core/src/lockstep_checks/__init__.py"
    init.write_text(init.read_text().replace(f'"{CURRENT}"', '"0.0.1"'))
    assert any("__init__.py: version 0.0.1" in p for p in check_release.check(repo))


def test_set_version_for_one_plugin(repo):
    check_release.set_version(repo, "9.3.0", "copilot-review-instructions")
    market = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text())
    versions = {p["name"]: p["version"] for p in market["plugins"]}
    assert versions["copilot-review-instructions"] == "9.3.0" and versions["lockstep-core"] == CURRENT
    assert market["metadata"]["version"] == CURRENT
    assert check_release.check(repo) == []
