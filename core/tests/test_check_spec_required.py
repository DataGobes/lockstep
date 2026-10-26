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
