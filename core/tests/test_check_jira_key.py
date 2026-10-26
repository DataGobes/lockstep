from pathlib import Path

from lockstep_checks.check_jira_key import _run, check_jira_key
from lockstep_checks.cli import run
from lockstep_checks.config import load_config
from lockstep_checks.spec import Resolution
from lockstep_checks.status import SpecStatus

CFG = load_config(Path("/no-such-dir"))
NO_SPEC = Resolution(state="no-match", branch="main")


def spec_for(key: str | None) -> Resolution:
    status = SpecStatus("approved", False, "data", key, None)
    return Resolution("found", "feature/0042-x", "0042", Path("specs/0042-x"), status)


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def test_key_in_title_passes():
    assert check_jira_key("MXAAI-42 Add churn features", "feature/0042-churn", NO_SPEC, CFG) == []


def test_key_in_branch_passes():
    assert check_jira_key("Add churn features", "feature/MXAAI-42-churn", NO_SPEC, CFG) == []


def test_missing_key_fails_with_example():
    (msg,) = errors(check_jira_key("Add churn features", "feature/0042-churn", NO_SPEC, CFG))
    assert "MXAAI-123" in msg


def test_other_project_key_does_not_count():
    assert errors(check_jira_key("PROJ-42 Add churn", "feature/0042-churn", NO_SPEC, CFG))


def test_key_must_match_spec():
    assert check_jira_key("MXAAI-42 x", "feature/0042-x", spec_for("MXAAI-42"), CFG) == []
    (msg,) = errors(check_jira_key("MXAAI-43 x", "feature/0042-x", spec_for("MXAAI-42"), CFG))
    assert "MXAAI-42" in msg and "0042" in msg


def test_multiple_keys_need_opt_in(tmp_path):
    assert errors(check_jira_key("MXAAI-1 MXAAI-2 x", None, NO_SPEC, CFG))
    (tmp_path / "lockstep.toml").write_text("[jira]\nmultiple_keys = true\n", encoding="utf-8")
    assert check_jira_key("MXAAI-1 MXAAI-2 x", None, NO_SPEC, load_config(tmp_path)) == []


def test_same_key_in_title_and_branch_is_one_key():
    assert check_jira_key("MXAAI-7 x", "feature/MXAAI-7-x", NO_SPEC, CFG) == []


def test_missing_title_warns_and_uses_branch():
    findings = check_jira_key(None, "feature/MXAAI-7-x", NO_SPEC, CFG)
    assert [f.level for f in findings] == ["warning"]


def test_end_to_end(repo, capsys):
    repo.commit({"README.md": "x\n"})
    args = ["--root", str(repo.root), "--branch", "feature/0042-x"]
    assert run("check_jira_key", "", _run, [*args, "--title", "Add x"]) == 1
    assert run("check_jira_key", "", _run, [*args, "--title", "MXAAI-9 Add x"]) == 0


def test_missing_key_passes_when_jira_is_optional(tmp_path):
    (tmp_path / "lockstep.toml").write_text("[jira]\nrequired = false\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert errors(check_jira_key("Add churn features", "feature/0042-churn", NO_SPEC, cfg)) == []
    # A key that is given is still checked against the spec.
    assert errors(check_jira_key("MXAAI-43 x", "feature/0042-x", spec_for("MXAAI-42"), cfg))
