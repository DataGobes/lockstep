"""Run with: python3 -m pytest plugins/lockstep-seed/tests (from the Lockstep repo root)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(PLUGIN / "core"))
probe = load("probe", PLUGIN / "scripts" / "probe.py")
compose = load("compose", PLUGIN / "scripts" / "compose.py")
ledger = load("ledger", PLUGIN / "scripts" / "ledger.py")
ENV = {
    "GIT_AUTHOR_NAME": "Test Person",
    "GIT_AUTHOR_EMAIL": "t001@example.invalid",
    "GIT_COMMITTER_NAME": "Test Person",
    "GIT_COMMITTER_EMAIL": "t001@example.invalid",
}


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**ENV, "HOME": str(root), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    ).stdout


def write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def commit(root, msg="change"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg, "--allow-empty")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(
        tmp_path,
        {
            "pyproject.toml": '[project]\nname = "sales"\n[tool.pytest.ini_options]\n',
            "uv.lock": "",
            "dbt_project.yml": "name: sales\n",
            "databricks.yml": "targets:\n  dev:\n    default: true\n  prod:\n    mode: production\n",
            "models/orders.sql": "select 1\n",
            "tests/test_orders.py": "def test_x():\n    pass\n",
            ".github/workflows/ci.yml": "on: push\n",
            "data/samples/orders.csv": "a,b\n",
        },
    )
    commit(tmp_path, "init")
    commit(tmp_path, "fix: late rows")
    return tmp_path


def catalog(root=None):
    return compose.load_catalog(compose.layers(root or Path("/nonexistent"), []))


def run_hook(root, event):
    p = subprocess.run(
        [sys.executable, str(root / ".workflow/core/protect_locked.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    return p.returncode, p.stderr


def seed(root, answers=""):
    a = root.parent / "answers.toml"
    a.write_text(answers, encoding="utf-8")
    assert compose.main(["apply", "--root", str(root), "--answers", str(a), "--by", "Test Person 001"]) == 0
    commit(root, "seed")


# ---------- probe ----------


def test_probe_finds_signals_commands_and_history(repo):
    p = probe.probe(repo)
    for s in ("dbt", "databricks", "prod_target", "pytest", "ci_github", "data_samples", "team_small", "has_tests"):
        assert s in p["signals"]
    assert p["commands"]["test"] == "uv run pytest"
    assert p["history"]["commits"] == 2 and p["history"]["fix_commits"] == 1


# ---------- plan: SEED.md section 2 ----------


def test_plan_starts_small_risk_and_context_only(repo):
    result = compose.plan(probe.probe(repo), {}, catalog())
    picked = {s["id"]: s["source"] for s in result["selected"]}
    assert picked == {"commands": "context", "guard-prod": "risk", "protect-secrets": "risk"}
    assert "spec-first" in {c["id"] for c in result["candidates"]}


def test_plan_evidence_answers_and_declines(repo):
    answers = {
        "pii": True,
        "evidence": [{"practice": "small-prs", "failure": "three PRs over 1,500 lines stalled"}],
        "decline": [{"practice": "guard-prod", "reason": "deploys are pipeline-only"}],
    }
    result = compose.plan(probe.probe(repo), answers, catalog())
    picked = {s["id"]: s for s in result["selected"]}
    assert picked["small-prs"]["reason"] == "three PRs over 1,500 lines stalled"
    assert picked["pii-in-company-tool"]["source"] == "answer"
    assert "guard-prod" not in picked
    assert any(c["id"] == "guard-prod" and "pipeline-only" in c["why"] for c in result["candidates"])


def test_plan_rejects_evidence_without_failure_and_unknown_ids(repo):
    with pytest.raises(compose.ComposeError):
        compose.plan(probe.probe(repo), {"evidence": [{"practice": "small-prs"}]}, catalog())
    with pytest.raises(compose.ComposeError):
        compose.plan(probe.probe(repo), {"evidence": [{"practice": "nope", "failure": "x"}]}, catalog())


def test_budget_caps_practices_at_seeding(repo):
    ev = [{"practice": p, "failure": "seen"} for p in ("small-prs", "spec-first", "glossary", "dbt-impact")]
    result = compose.plan(probe.probe(repo), {"evidence": ev}, catalog())
    w = compose.initial_workflow(probe.probe(repo), result)
    assert any("budget is 5" in e for e in compose.budget_errors(w, catalog()))
    assert compose.main(["plan", "--root", str(repo)]) == 0


# ---------- apply, render, grow ----------


def test_apply_renders_and_logs(repo):
    write(
        repo,
        {
            ".claude/settings.json": json.dumps({"permissions": {"deny": ["Read(./mine)"]}}),
            "AGENTS.md": "# Sales\n\nOur own words.\n",
        },
    )
    commit(repo)
    seed(repo, "prod_reachable = true\n")
    agents = (repo / "AGENTS.md").read_text()
    assert "Our own words." in agents and "uv run pytest" in agents and "seed:end" in agents
    assert (repo / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert "Read(./mine)" in settings["permissions"]["deny"]
    assert "Bash(databricks bundle deploy -t prod*)" in settings["permissions"]["deny"]
    assert (repo / ".github/workflows/seed-core.yml").is_file()
    events = ledger.events(repo)
    assert events[0]["action"] == "seed" and events[0]["baseline"]["commits"] == 3
    assert {e["practice"] for e in events if e["action"] == "add"} == {"commands", "guard-prod", "protect-secrets"}
    assert compose.main(["apply", "--root", str(repo)]) == 2  # already seeded


def test_add_and_remove_rerender_and_log(repo):
    seed(repo)
    assert compose.main(["add", "--root", str(repo), "--practice", "small-prs"]) == 2  # no reason
    assert compose.main(["add", "--root", str(repo), "--practice", "small-prs", "--reason", "PRs stalled"]) == 0
    assert "under about 400 changed lines" in (repo / "AGENTS.md").read_text()
    assert compose.main(["remove", "--root", str(repo), "--practice", "protect-secrets", "--reason", "synthetic"]) == 0
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert "Read(./data/samples/**)" not in settings["permissions"]["deny"]
    assert len(settings["hooks"]["PreToolUse"]) == 1
    assert [e["action"] for e in ledger.events(repo)][-2:] == ["add", "remove"]
    assert "small-prs" in "\n".join(ledger.report(repo))


def test_repo_local_practice_layer(repo):
    seed(repo)
    write(
        repo,
        {
            ".workflow/practices/notebooks.toml": 'id = "notebooks"\ntitle = "t"\nprevents = "p"\n'
            'start = "evidence"\n[render]\nagents_md = ["Never commit notebook outputs."]\n'
        },
    )
    assert compose.main(["add", "--root", str(repo), "--practice", "notebooks", "--reason", "outputs leaked"]) == 0
    assert "Never commit notebook outputs." in (repo / "AGENTS.md").read_text()


# ---------- the fixed core ----------


def test_hook_blocks_locked_tests_and_workflow_records(repo):
    seed(repo)
    write(repo, {".workflow/locks.toml": '[[lock]]\npath = "tests/test_orders.py"\nspec = "specs/0001-x.md"\n'})
    assert run_hook(repo, {"tool_name": "Edit", "tool_input": {"file_path": "tests/test_orders.py"}})[0] == 2
    assert (
        run_hook(repo, {"tool_name": "Bash", "tool_input": {"command": "sed -i s/a/b/ tests/test_orders.py"}})[0] == 2
    )
    assert run_hook(repo, {"tool_name": "Write", "tool_input": {"file_path": ".workflow/locks.toml"}})[0] == 2
    assert run_hook(repo, {"toolName": "edit", "toolArgs": '{"path": "tests/test_orders.py"}'})[0] == 2
    assert (
        run_hook(repo, {"tool_name": "Bash", "tool_input": {"command": "uv run pytest tests/test_orders.py"}})[0] == 0
    )
    assert run_hook(repo, {"tool_name": "Edit", "tool_input": {"file_path": "models/orders.sql"}})[0] == 0
    p = subprocess.run(
        [sys.executable, str(repo / ".workflow/core/protect_locked.py")],
        input="not json",
        capture_output=True,
        text=True,
        cwd=repo,
        check=False,
    )
    assert p.returncode == 2  # fails closed


def check(repo, *args):
    p = subprocess.run(
        [sys.executable, str(repo / ".workflow/core/check_core.py"), "--root", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout


def test_check_core(repo):
    seed(repo)
    git(repo, "branch", "base")
    write(
        repo,
        {
            "specs/0001-active.md": "- AC-001: bought in 90 days\n- AC-002: logins don't count\n",
            "tests/test_active.py": '@pytest.mark.ac("0001/AC-001")\n',
            ".workflow/locks.toml": '[[lock]]\npath = "tests/test_active.py"\nspec = "specs/0001-active.md"\n',
        },
    )
    commit(repo)
    code, out = check(repo, "--base", "base")
    assert code == 1 and "AC-002 has no test" in out
    write(repo, {"tests/test_logins.py": '@pytest.mark.ac("0001/AC-002")\n'})
    commit(repo)
    assert check(repo, "--base", "base")[0] == 0
    git(repo, "branch", "base2")
    write(repo, {"tests/test_active.py": '@pytest.mark.ac("0001/AC-001")\n# bent\n'})
    commit(repo)
    code, out = check(repo, "--base", "base2")
    assert code == 1 and "locked test and changed" in out
    assert check(repo, "--base", "base2", "--title", "[test-change] fix test")[0] == 0


def test_check_core_ledger_is_append_only(repo):
    seed(repo)
    git(repo, "branch", "base")
    path = repo / ".workflow/ledger.jsonl"
    path.write_text(path.read_text().splitlines()[1] + "\n")
    commit(repo)
    code, out = check(repo, "--base", "base")
    assert code == 1 and "may only be appended to" in out
