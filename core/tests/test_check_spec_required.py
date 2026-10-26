from pathlib import Path

import pytest

from lockstep_checks.check_spec_required import _run, check_spec_required
from lockstep_checks.cli import run
from lockstep_checks.config import load_config
from lockstep_checks.gitdiff import ChangedFile
from lockstep_checks.spec import Resolution
from lockstep_checks.status import SpecStatus

CFG = load_config(Path("/no-such-dir"))
NO_SPEC = Resolution(state="no-match", branch="x")
CODE = ChangedFile("src/app.py", "M")


def spec(status: str, branch: str = "feature/0042-churn") -> Resolution:
    st = SpecStatus(status, False, "data", "MXAAI-42", None)
    return Resolution("found", branch, "0042", Path("specs/0042-churn"), st)


def errors(findings):
    return [f.message for f in findings if f.level == "error"]


def test_docs_and_specs_never_need_a_spec():
    files = [
        ChangedFile("docs/how.md", "M"),
        ChangedFile("specs/0042-churn/spec.md", "A"),
        ChangedFile("README.md", "M"),
    ]
    assert check_spec_required(files, "main-ish", NO_SPEC, CFG) == []


def test_deleting_code_alone_needs_no_spec():
    assert check_spec_required([ChangedFile("src/old.py", "D")], "cleanup", NO_SPEC, CFG) == []


def test_code_without_a_spec_fails_and_names_the_lanes():
    found = errors(check_spec_required([CODE, ChangedFile("src/b.py", "A")], "my-branch", NO_SPEC, CFG))
    assert len(found) == 1
    assert "src/app.py and 1 more" in found[0] and "chore/" in found[0] and "bugfix/" in found[0]


def test_chore_lane_needs_nothing():
    assert check_spec_required([CODE], "chore/bump-ruff", NO_SPEC, CFG) == []


@pytest.mark.parametrize("status", ["tests-locked", "implemented"])
def test_feature_with_locked_spec_passes(status):
    assert check_spec_required([CODE], "feature/0042-churn", spec(status), CFG) == []


@pytest.mark.parametrize("status", ["draft", "approved"])
def test_feature_before_tests_are_locked_fails(status):
    found = check_spec_required([CODE], "feature/0042-churn", spec(status), CFG)
    assert errors(found) and found[0].path == "specs/0042-churn/status.yml"
    assert status in found[0].message


def test_test_pr_may_add_stubs_once_approved():
    assert check_spec_required([CODE], "test/0042-churn", spec("approved", "test/0042-churn"), CFG) == []
    assert errors(check_spec_required([CODE], "test/0042-churn", spec("draft", "test/0042-churn"), CFG))


def test_spec_pr_must_not_change_code():
    found = errors(check_spec_required([CODE], "spec/0042-churn", spec("draft", "spec/0042-churn"), CFG))
    assert "src/app.py" in found[0]


def test_missing_spec_folder_fails():
    missing = Resolution("missing", "feature/0042-churn", "0042")
    assert "does not exist" in errors(check_spec_required([CODE], "feature/0042-churn", missing, CFG))[0]


def test_bugfix_needs_report_and_new_regression_test():
    found = errors(check_spec_required([CODE], "bugfix/MXAAI-7-null-prices", NO_SPEC, CFG))
    assert len(found) == 2
    assert "specs/bug-reports/" in found[0] and "regression test" in found[1]


def test_bugfix_with_report_and_new_test_passes():
    files = [
        CODE,
        ChangedFile("specs/bug-reports/MXAAI-7-null-prices.md", "A"),
        ChangedFile("tests/test_bug_7.py", "A"),
    ]
    assert check_spec_required(files, "hotfix/MXAAI-7-null-prices", NO_SPEC, CFG) == []


def test_editing_the_template_is_not_a_bug_report():
    files = [CODE, ChangedFile("specs/bug-reports/_template.md", "M"), ChangedFile("tests/test_bug_7.py", "A")]
    assert "bug report" in errors(check_spec_required(files, "bugfix/MXAAI-7", NO_SPEC, CFG))[0]


def test_changing_an_existing_test_is_not_a_regression_test():
    files = [CODE, ChangedFile("specs/bug-reports/MXAAI-7.md", "A"), ChangedFile("tests/test_a.py", "M")]
    assert "regression test" in errors(check_spec_required(files, "bugfix/MXAAI-7", NO_SPEC, CFG))[0]


def test_lanes_are_configurable(tmp_path):
    (tmp_path / "lockstep.toml").write_text('[lanes]\nchore = ["maint/"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert check_spec_required([CODE], "maint/deps", NO_SPEC, cfg) == []
    assert errors(check_spec_required([CODE], "chore/deps", NO_SPEC, cfg))


@pytest.mark.parametrize("toml", ['chore = ["fix/"]\nbugfix = ["fix/"]', 'chore = ["chore"]'])
def test_bad_lanes_are_a_config_error(tmp_path, toml):
    (tmp_path / "lockstep.toml").write_text(f"[lanes]\n{toml}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="lanes"):
        load_config(tmp_path)


def test_end_to_end(repo, capsys):
    repo.commit({"src/app.py": "x = 1\n"})
    repo.branch("feature/0042-churn")
    repo.commit({"specs/0042-churn/status.yml": "status: approved\npii: no\ntrack: data\njira: MXAAI-42\n"})
    repo.commit({"src/app.py": "x = 2\n"})
    assert run("check_spec_required", "", _run, ["--root", str(repo.root), "--base", "main"]) == 1
    assert "needs it tests-locked or implemented" in capsys.readouterr().out


QUICK_SPEC = """\
## 1. Problem and outcome
## 2. Scope / non-goals
## 3. Acceptance criteria
{criteria}
## 4. Interfaces and data contract
## 5. Test and eval plan
## 6. Risks, rollout, rollback
## 7. Open questions
"""


def quick(tmp_path, n_criteria: int, limit: int, design: bool = False):
    (tmp_path / "lockstep.toml").write_text(f"[specs]\nquick_max_criteria = {limit}\n")
    folder = tmp_path / "specs" / "0042-churn"
    folder.mkdir(parents=True)
    criteria = "\n".join(f"- AC-00{i} THE SYSTEM SHALL do {i}." for i in range(1, n_criteria + 1))
    (folder / "spec.md").write_text(QUICK_SPEC.format(criteria=criteria))
    st = SpecStatus("tests-locked", False, "data", "MXAAI-42", "abc1234", design=design)
    res = Resolution("found", "test/0042-churn", "0042", folder, st)
    files = [ChangedFile("specs/0042-churn/spec.md", "A"), ChangedFile("tests/test_churn.py", "A")]
    return check_spec_required(files, "test/0042-churn", res, load_config(tmp_path))


def test_quick_lane_takes_a_small_spec_in_the_test_pr(tmp_path):
    assert quick(tmp_path, 2, 3) == []


def test_quick_lane_off_needs_a_spec_pr(tmp_path):
    found = errors(quick(tmp_path, 1, 0))
    assert "without a spec PR of its own" in found[0] and "quick_max_criteria = 0" in found[0]


def test_quick_lane_refuses_a_bigger_spec(tmp_path):
    assert "it has 4 criteria and the quick lane takes at most 3" in errors(quick(tmp_path, 4, 3))[0]


def test_quick_lane_refuses_a_spec_with_the_design_step(tmp_path):
    assert "research and design step" in errors(quick(tmp_path, 1, 3, design=True))[0]


def test_test_pr_for_a_spec_already_merged_is_not_the_quick_lane():
    files = [ChangedFile("specs/0042-churn/spec.md", "M"), ChangedFile("tests/test_churn.py", "A")]
    assert check_spec_required(files, "test/0042-churn", spec("tests-locked", "test/0042-churn"), CFG) == []


def test_quick_max_criteria_cannot_be_negative(tmp_path):
    (tmp_path / "lockstep.toml").write_text("[specs]\nquick_max_criteria = -1\n")
    with pytest.raises(Exception, match="quick_max_criteria"):
        load_config(tmp_path)


def baseline(status: str, branch: str = "baseline/0042-churn") -> Resolution:
    st = SpecStatus(status, False, "data", "MXAAI-42", "abc1234" if status == "implemented" else None, kind="baseline")
    return Resolution("found", branch, "0042", Path("specs/0042-churn"), st)


TEST = ChangedFile("tests/test_churn_today.py", "A")


def test_baseline_pr_with_passing_tests_and_implemented_spec_passes():
    files = [TEST, ChangedFile("tests/test_old.py", "M"), ChangedFile("specs/0042-churn/spec.md", "A")]
    assert check_spec_required(files, "baseline/0042-churn", baseline("implemented"), CFG) == []


def test_baseline_pr_with_only_the_spec_needs_no_status():
    files = [ChangedFile("specs/0042-churn/spec.md", "A")]
    assert check_spec_required(files, "baseline/0042-churn", baseline("draft"), CFG) == []


@pytest.mark.parametrize("status", ["draft", "approved"])
def test_baseline_pr_adding_tests_must_end_implemented(status):
    found = errors(check_spec_required([TEST], "baseline/0042-churn", baseline(status), CFG))
    assert len(found) == 1 and "set status: implemented" in found[0] and status in found[0]


def test_baseline_pr_must_not_change_code():
    found = errors(check_spec_required([TEST, CODE], "baseline/0042-churn", baseline("implemented"), CFG))
    assert len(found) == 1 and "src/app.py" in found[0] and "changes only tests, specs and docs" in found[0]


def test_baseline_branch_needs_a_baseline_spec():
    found = errors(check_spec_required([TEST], "baseline/0042-churn", spec("implemented", "baseline/0042-churn"), CFG))
    assert "kind: baseline" in found[0]


@pytest.mark.parametrize("branch", ["feature/0042-churn", "test/0042-churn"])
def test_baseline_spec_cannot_be_built_on(branch):
    found = errors(check_spec_required([CODE], branch, baseline("implemented", branch), CFG))
    assert "is a baseline" in found[0] and "baseline/0042-churn" in found[0]


def test_baseline_branch_outside_a_custom_branch_pattern_says_so(tmp_path):
    (tmp_path / "lockstep.toml").write_text("[lockstep]\nbranch_pattern = '^(?:feature|test|spec)/(?P<id>\\\\d{4})-'\n")
    cfg = load_config(tmp_path)
    found = errors(check_spec_required([TEST], "baseline/0042-churn", NO_SPEC, cfg))
    assert "add 'baseline'" in found[0]


def test_feature_pr_into_main_must_mark_the_spec_implemented():
    found = check_spec_required([CODE], "feature/0042-churn", spec("tests-locked"), CFG, into_main="error")
    assert errors(found) and "set status: implemented" in found[0].message
    assert check_spec_required([CODE], "feature/0042-churn", spec("implemented"), CFG, into_main="error") == []
    assert check_spec_required([CODE], "feature/0042-churn", spec("tests-locked"), CFG) == []


def test_marking_implemented_is_a_warning_locally_and_an_error_in_the_pr_into_main(monkeypatch):
    from lockstep_checks.check_spec_required import _into_main

    monkeypatch.delenv("SYSTEM_PULLREQUEST_TARGETBRANCH", raising=False)
    assert _into_main("origin/main") == "warning"
    assert _into_main("origin/feature/0042-churn") is None
    monkeypatch.setenv("SYSTEM_PULLREQUEST_TARGETBRANCH", "refs/heads/main")
    assert _into_main("origin/main") == "error"


def test_test_change_pr_for_a_shipped_spec_uses_its_test_branch():
    assert (
        check_spec_required(
            [ChangedFile("tests/test_churn.py", "M")],
            "test/0042-churn-fix",
            spec("implemented", "test/0042-churn-fix"),
            CFG,
        )
        == []
    )
