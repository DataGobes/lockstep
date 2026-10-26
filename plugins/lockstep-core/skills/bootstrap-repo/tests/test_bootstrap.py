"""Run with: python3 -m pytest plugins/lockstep-core/skills/bootstrap-repo/tests (from the Lockstep repo root)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("bootstrap", HERE.parent / "scripts" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(spec)
sys.modules["bootstrap"] = bootstrap
spec.loader.exec_module(bootstrap)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def run(repo, *extra):
    return bootstrap.main(["--root", str(repo), "--source", str(LOCKSTEP), *extra])


def kinds(repo, **kw):
    actions = bootstrap.plan(repo, LOCKSTEP, "source: test\n", kw.get("tracks", ["data", "ai"]), ["MXAAI"])
    return {a.path: a.kind for a in actions}


def test_fresh_repo_gets_everything(repo):
    plan = kinds(repo)
    assert set(plan.values()) == {"create"}
    for path in (
        "AGENTS.md",
        ".claude/settings.json",
        ".lockstep/hooks/run-hook.sh",
        "specs/_template/spec.md",
        ".lockstep/pipelines/lockstep-pr.yml",
        ".lockstep/src/lockstep_checks/config.py",
        "lockstep.toml",
    ):
        assert path in plan
    assert not any("__pycache__" in p or p.endswith(".pyc") for p in plan)


def test_plan_alone_changes_nothing(repo, capsys):
    assert run(repo) == 0
    assert sorted(p.name for p in repo.iterdir()) == [".git"]
    assert "create  AGENTS.md" in capsys.readouterr().out


def test_apply_then_nothing_left_to_do(repo):
    assert run(repo, "--apply") == 0
    assert set(kinds(repo).values()) <= {"same", "update"}  # update: only the VERSION origin text differs here
    assert (repo / ".lockstep" / "hooks" / "run-hook.sh").stat().st_mode & 0o111


def test_repo_files_are_never_overwritten(repo):
    run(repo, "--apply")
    (repo / "AGENTS.md").write_text("# Our own agent notes\n", encoding="utf-8")
    assert kinds(repo)["AGENTS.md"] == "merge"
    run(repo, "--apply")
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# Our own agent notes\n"


def test_managed_files_are_updated_and_pruned(repo):
    run(repo, "--apply")
    core = repo / ".lockstep" / "src" / "lockstep_checks"
    (core / "config.py").write_text("# edited by hand\n", encoding="utf-8")
    (core / "old_check.py").write_text("", encoding="utf-8")
    plan = kinds(repo)
    assert plan[".lockstep/src/lockstep_checks/config.py"] == "update"
    assert plan[".lockstep/src/lockstep_checks/old_check.py"] == "remove"
    run(repo, "--apply")
    assert not (core / "old_check.py").exists()
    assert (core / "config.py").read_bytes() == (LOCKSTEP / "core/src/lockstep_checks/config.py").read_bytes()


def test_config_gets_the_chosen_tracks_and_jira_keys(repo):
    assert run(repo, "--apply", "--tracks", "data", "--jira", "MXAAI,OPS") == 0
    sys.path.insert(0, str(repo / ".lockstep" / "src"))
    try:
        from lockstep_checks.config import load_config

        cfg = load_config(repo)
    finally:
        sys.path.pop(0)
    assert cfg.tracks == ("data",)
    assert cfg.jira_projects == ("MXAAI", "OPS")


def test_installed_checks_and_hooks_run(repo):
    run(repo, "--apply")
    env = {"PYTHONPATH": str(repo / ".lockstep" / "src"), "PATH": "/usr/bin:/bin"}
    p = subprocess.run(
        [sys.executable, "-m", "lockstep_checks.check_review_rules", "--root", str(repo), "--write"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "lockstep:review-rules" in (repo / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    # Running the checks compiled .lockstep/src; the bytecode must not show up as a change in the repo.
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], check=True, capture_output=True, text=True
    )
    assert "__pycache__" not in status.stdout and ".pyc" not in status.stdout


@pytest.mark.parametrize("args", [["--tracks", "web"], ["--jira", "mxaai"]])
def test_bad_options_are_rejected(repo, args):
    with pytest.raises(SystemExit):
        run(repo, *args)


def test_not_a_lockstep_checkout(repo, tmp_path_factory):
    with pytest.raises(bootstrap.BootstrapError, match="not a Lockstep checkout"):
        bootstrap.plan(repo, tmp_path_factory.mktemp("empty"), "", ["data"], ["MXAAI"])


def test_fetches_a_git_ref_and_records_it(repo, tmp_path_factory):
    # A copy with a named branch: this checkout may be detached, as in CI.
    source = tmp_path_factory.mktemp("source")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "fetch", "-q", str(LOCKSTEP), "HEAD:refs/heads/release"], check=True)
    url = source.as_uri()
    assert bootstrap.main(["--root", str(repo), "--git", url, "--ref", "release", "--apply"]) == 0
    version = (repo / ".lockstep" / "VERSION").read_text(encoding="utf-8")
    assert version.startswith(f"source: {url}@") and "commit: " in version


def test_unknown_ref_fails_cleanly(repo, capsys):
    assert bootstrap.main(["--root", str(repo), "--git", LOCKSTEP.as_uri(), "--ref", "no-such-ref"]) == 1
    assert "cannot fetch Lockstep no-such-ref" in capsys.readouterr().err


def test_branch_policy_script_refuses_until_filled_in(repo):
    run(repo, "--apply")
    script = repo / "scripts" / "ado" / "branch-policy.sh"
    assert script.stat().st_mode & 0o111  # keeps the template's executable bit
    p = subprocess.run([str(script)], check=False, capture_output=True, text=True)
    assert p.returncode == 1 and "Fill in the variables" in p.stderr
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0


def test_no_jira_switches_the_key_off(repo):
    run(repo, "--apply", "--no-jira")
    text = (repo / "lockstep.toml").read_text(encoding="utf-8")
    assert "required = false" in text and "required = true" not in text
