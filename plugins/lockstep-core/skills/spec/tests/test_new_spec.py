"""Run with: python3 -m pytest plugins/lockstep-core/skills/spec/tests (from the Lockstep repo root)."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("new_spec", HERE.parent / "scripts" / "new_spec.py")
new_spec = importlib.util.module_from_spec(spec)
sys.modules["new_spec"] = new_spec
spec.loader.exec_module(new_spec)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    shutil.copytree(LOCKSTEP / "templates" / "specs" / "_template", tmp_path / "specs" / "_template")
    return tmp_path


def lockstep_core():
    # The spec must pass the same parsers the hooks and CI use.
    sys.path.insert(0, str(LOCKSTEP / "core" / "src"))
    try:
        from lockstep_checks.config import load_config
        from lockstep_checks.specdoc import parse_spec
        from lockstep_checks.status import parse_status
    finally:
        sys.path.pop(0)
    return load_config, parse_spec, parse_status


def test_first_spec_is_0001(repo):
    out = new_spec.create(repo, "Churn features", "data", "no", "MXAAI-123")
    assert out == {"id": "0001", "spec_dir": "specs/0001-churn-features", "branch": "spec/0001-churn-features"}
    load_config, parse_spec, parse_status = lockstep_core()
    status = parse_status((repo / out["spec_dir"] / "status.yml").read_text(encoding="utf-8"), load_config(repo))
    assert (status.status, status.track, status.pii, status.jira) == ("draft", "data", False, "MXAAI-123")
    text = (repo / out["spec_dir"] / "spec.md").read_text(encoding="utf-8")
    assert "id: 0001" in text and "# Churn features" in text and "0001/AC-001" in text and "0042" not in text
    assert parse_spec(text).problems == []


def test_next_id_counts_specs_on_origin_main(repo):
    (repo / "specs" / "0007-old").mkdir()
    remote = repo.parent / "remote"
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", "commit", "-qm", "x")
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    # Someone else merged spec 0012 on main since this branch started.
    other = repo.parent / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    (other / "specs" / "0012-theirs").mkdir()
    (other / "specs" / "0012-theirs" / "spec.md").write_text("x\n", encoding="utf-8")
    git(other, "add", "-A")
    git(other, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 002", "commit", "-qm", "y")
    git(other, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "origin")
    assert new_spec.create(repo, "Mine", "ai", "no", None)["id"] == "0013"


def test_draft_without_jira_and_pii_yes(repo):
    out = new_spec.create(repo, "Customer contact cleanup", "data", "yes", None)
    load_config, _, parse_status = lockstep_core()
    status = parse_status((repo / out["spec_dir"] / "status.yml").read_text(encoding="utf-8"), load_config(repo))
    assert status.pii is True and status.jira is None


def test_taken_id_is_refused(repo):
    new_spec.create(repo, "One", "data", "no", None)
    with pytest.raises(new_spec.SpecError, match="already used"):
        new_spec.create(repo, "Two", "data", "no", None, spec_id="0001")


def test_missing_template_points_to_bootstrap(tmp_path):
    with pytest.raises(new_spec.SpecError, match="bootstrap-repo"):
        new_spec.create(tmp_path, "One", "data", "no", None)


@pytest.mark.parametrize(
    "title, slug",
    [("Churn features", "churn-features"), ("Größe & Gewicht — v2!", "grosse-gewicht-v2"), ("???", "spec")],
)
def test_slugify(title, slug):
    assert new_spec.slugify(title) == slug


@pytest.mark.parametrize("args", [["--jira", "mxaai-1"], ["--id", "42"], ["--slug", "Not OK"], ["--track", "web"]])
def test_cli_rejects_bad_input(repo, args):
    with pytest.raises(SystemExit):
        new_spec.main(["--root", str(repo), "--title", "x", "--track", "data", "--pii", "no", *args])


def test_design_docs_only_on_request(repo):
    plain = new_spec.create(repo, "Small change", "data", "no", "MXAAI-1")
    assert sorted(p.name for p in (repo / plain["spec_dir"]).iterdir()) == ["spec.md", "status.yml"]
    big = new_spec.create(repo, "Churn platform", "data", "no", "MXAAI-2", design=True)
    folder = repo / big["spec_dir"]
    assert sorted(p.name for p in folder.iterdir()) == ["design.md", "research.md", "spec.md", "status.yml"]
    assert (folder / "research.md").read_text(encoding="utf-8").startswith("# Research: Churn platform\n")
    load_config, _, parse_status = lockstep_core()
    assert parse_status((folder / "status.yml").read_text(encoding="utf-8"), load_config(repo)).design is True


def test_capability_goes_into_status(repo):
    out = new_spec.create(repo, "Daily churn", "data", "no", "MXAAI-3", capability="churn-scoring")
    load_config, _, parse_status = lockstep_core()
    status = parse_status((repo / out["spec_dir"] / "status.yml").read_text(encoding="utf-8"), load_config(repo))
    assert status.capability == "churn-scoring"


def test_baseline_spec_uses_the_baseline_template_and_branch(repo):
    out = new_spec.create(repo, "Pricing as it works today", "data", "no", "MXAAI-7", baseline=True)
    assert out["branch"] == "baseline/0001-pricing-as-it-works-today"
    folder = repo / out["spec_dir"]
    assert not (folder / "baseline").exists() and not (folder / "design").exists()
    load_config, parse_spec, parse_status = lockstep_core()
    cfg = load_config(repo)
    status = parse_status((folder / "status.yml").read_text(), cfg)
    assert status.kind == "baseline" and status.status == "draft"
    text = (folder / "spec.md").read_text()
    assert "# Pricing as it works today" in text and "Observed in:" in text and "0001/AC-001" in text
    assert parse_spec(text).problems == []


def test_change_spec_stays_a_change(repo):
    out = new_spec.create(repo, "Churn features", "data", "no", "MXAAI-123")
    load_config, _, parse_status = lockstep_core()
    status = parse_status((repo / out["spec_dir"] / "status.yml").read_text(), load_config(repo))
    assert status.kind == "change"


def test_baseline_without_its_template_creates_nothing(repo):
    shutil.rmtree(repo / "specs" / "_template" / "baseline")
    with pytest.raises(new_spec.SpecError, match="baseline"):
        new_spec.create(repo, "Pricing", "data", "no", None, baseline=True)
    assert sorted(p.name for p in (repo / "specs").iterdir()) == ["_template"]
