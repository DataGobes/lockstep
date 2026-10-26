"""Spec 0001: the PR trust summary, rendered from evidence files."""

import time

import pytest
from trust_fixtures import (
    CRITERIA,
    checks,
    clean_evidence,
    entry,
    feature_pr,
    head,
    into_feature_branch,
    lock,
    mutation,
    quality,
    signal,
)

from lockstep_checks.trust_summary import Context, render


def criteria_rows(summary):
    return {c["id"]: c["tests"] for c in summary.data["criteria"]}


def results(summary, ac):
    return {t["node"]: t["result"] for t in criteria_rows(summary)[ac]}


@pytest.mark.ac("0001/AC-004")
def test_all_clean_starts_with_one_line_saying_so():
    summary = render(clean_evidence(), feature_pr())
    assert summary.data["verdict"] == "clean"
    first = head(summary.markdown)[0]
    assert "3 of 3 criteria" in first
    assert "clean" in first.lower()


@pytest.mark.ac("0001/AC-004")
def test_clean_headline_counts_only_criteria_with_a_passing_test():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"]),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"], "red", "AssertionError: assert 1 == 0"),
    }
    summary = render([quality(tests), checks(), lock(), mutation()], feature_pr())
    assert summary.data["verdict"] != "clean"
    assert "1 of 3 criteria" in summary.markdown


@pytest.mark.ac("0001/AC-005")
@pytest.mark.parametrize("failing", [1, 2])
def test_not_clean_starts_with_each_failing_signal_and_its_next_step(failing):
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"], "red", "AssertionError: assert 0.1 == 0.25"),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"]),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"]),
    }
    coverage = (62.0, 80) if failing == 2 else (86.0, 80)
    summary = render([quality(tests, coverage), checks(), lock(), mutation()], feature_pr())
    assert summary.data["verdict"] == "attention"
    bad = [s for s in summary.data["signals"] if s["state"] == "not_clean"]
    assert len(bad) == failing
    assert {s["name"] for s in bad} == ({"tests", "coverage"} if failing == 2 else {"tests"})
    top = head(summary.markdown)[:failing]
    for s in bad:
        assert s["next_step"], f"{s['name']} has no next step"
        assert any(s["next_step"] in line for line in top), f"{s['name']}'s next step is not at the top: {top}"


@pytest.mark.ac("0001/AC-006")
def test_lists_each_criterion_with_its_tests_and_results():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"]),
        "tests/test_churn.py::test_rate_rounding": entry(["0042/AC-001"], "red", "AssertionError: 0.33 != 0.333"),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"], "skipped", "skip"),
    }
    summary = render([quality(tests), checks(), lock(), mutation()], feature_pr())
    assert [c["id"] for c in summary.data["criteria"]] == list(CRITERIA)
    assert results(summary, "0042/AC-001") == {
        "tests/test_churn.py::test_rate": "passed",
        "tests/test_churn.py::test_rate_rounding": "failed",
    }
    assert criteria_rows(summary)["0042/AC-002"] == []
    assert results(summary, "0042/AC-003") == {"tests/test_churn.py::test_cap": "skipped"}
    assert "0042/AC-002" in summary.markdown and "tests/test_churn.py::test_rate_rounding" in summary.markdown


@pytest.mark.ac("0001/AC-006")
def test_superseded_criteria_are_left_out():
    summary = render(clean_evidence(), feature_pr(superseded=frozenset({"0042/AC-002"})))
    assert [c["id"] for c in summary.data["criteria"]] == ["0042/AC-001", "0042/AC-003"]
    assert "0042/AC-002" not in summary.markdown


@pytest.mark.ac("0001/AC-006")
def test_a_test_that_did_not_run_is_shown_as_not_run():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"]),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"], "not-run"),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"]),
    }
    summary = render([quality(tests), checks(), lock(), mutation()], feature_pr())
    assert results(summary, "0042/AC-002") == {"tests/test_churn.py::test_empty": "not_run"}
    assert signal(summary, "tests")["state"] == "not_clean"


@pytest.mark.ac("0001/AC-007")
def test_into_feature_branch_assertion_and_not_implemented_are_red_as_expected():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"], "red", "AssertionError: assert None == 0.25"),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"], "red", "NotImplementedError"),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"], "red", "AssertionError: assert None == 1.0"),
    }
    summary = render([quality(tests, coverage=None), checks(), mutation()], into_feature_branch())
    for ac in CRITERIA:
        assert set(results(summary, ac).values()) == {"red_expected"}
    assert signal(summary, "tests")["state"] == "clean"


@pytest.mark.ac("0001/AC-007")
@pytest.mark.parametrize(
    ("result", "detail", "shown"),
    [
        ("passes", "", "passed"),
        ("wrong-reason", "ImportError: cannot import name 'churn_rate'", "red_wrong_reason"),
        ("wrong-reason", "TypeError: churn_rate() takes 1 positional argument", "red_wrong_reason"),
    ],
)
def test_into_feature_branch_a_pass_or_wrong_error_is_not_clean(result, detail, shown):
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"], result, detail),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"], "red", "NotImplementedError"),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"], "red", "AssertionError: assert None == 1.0"),
    }
    summary = render([quality(tests, coverage=None), checks(), mutation()], into_feature_branch())
    assert results(summary, "0042/AC-001") == {"tests/test_churn.py::test_rate": shown}
    assert signal(summary, "tests")["state"] == "not_clean"
    assert summary.data["verdict"] == "attention"


@pytest.mark.ac("0001/AC-007")
def test_only_the_spec_new_test_files_are_excused():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"], "red", "AssertionError: assert None == 0.25"),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"], "red", "NotImplementedError"),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"], "red", "AssertionError: assert None == 1.0"),
        "tests/test_billing.py::test_total": entry([], "red", "AssertionError: assert 10 == 12"),
    }
    summary = render([quality(tests, coverage=None), checks(), mutation()], into_feature_branch())
    assert signal(summary, "tests")["state"] == "not_clean"
    assert "tests/test_billing.py::test_total" in summary.markdown


@pytest.mark.ac("0001/AC-007")
def test_into_main_red_is_never_expected():
    tests = {
        "tests/test_churn.py::test_rate": entry(["0042/AC-001"], "red", "AssertionError: assert None == 0.25"),
        "tests/test_churn.py::test_empty": entry(["0042/AC-002"]),
        "tests/test_churn.py::test_cap": entry(["0042/AC-003"]),
    }
    summary = render([quality(tests), checks(), lock(), mutation()], feature_pr(expected_red=("tests/test_churn.py",)))
    assert results(summary, "0042/AC-001") == {"tests/test_churn.py::test_rate": "failed"}
    assert signal(summary, "tests")["state"] == "not_clean"


@pytest.mark.ac("0001/AC-008")
def test_shows_the_lock_commit_and_that_nothing_changed_since():
    summary = render(clean_evidence(), feature_pr())
    s = signal(summary, "lock")
    assert s["state"] == "clean"
    assert s["commit"] == "3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39"
    assert "3f2a9c1" in summary.markdown and "2026-10-20" in summary.markdown


@pytest.mark.ac("0001/AC-008")
def test_a_protected_file_changed_since_the_lock_is_not_clean():
    summary = render([quality(), checks(), lock(["tests/test_churn.py"]), mutation()], feature_pr())
    s = signal(summary, "lock")
    assert s["state"] == "not_clean"
    assert s["changed_since"] == ["tests/test_churn.py"]
    assert "tests/test_churn.py" in summary.markdown


@pytest.mark.ac("0001/AC-009")
def test_tamper_check_clean_is_shown_as_clean():
    s = signal(render(clean_evidence(), feature_pr()), "tamper")
    assert s["state"] == "clean"


@pytest.mark.ac("0001/AC-009")
def test_tamper_findings_are_not_clean():
    finding = {"level": "error", "message": "modifies a locked test", "path": "tests/test_churn.py", "line": None}
    summary = render([quality(), checks([finding]), lock(), mutation()], feature_pr())
    assert signal(summary, "tamper")["state"] == "not_clean"
    assert summary.data["verdict"] == "attention"


@pytest.mark.ac("0001/AC-009")
def test_a_test_change_pr_lists_each_file_as_an_approved_change():
    findings = [
        {"level": "warning", "message": "modifies a locked test", "path": "tests/test_churn.py", "line": None},
        {"level": "warning", "message": "adds skip", "path": "tests/test_cap.py", "line": 12},
    ]
    ctx = feature_pr(title="[test-change] MXAAI-42 Fix the churn cap test")
    summary = render([quality(), checks(findings, test_change=True), lock(), mutation()], ctx)
    s = signal(summary, "tamper")
    assert s["state"] == "approved_change"
    assert s["approved_changes"] == ["tests/test_cap.py", "tests/test_churn.py"]
    assert summary.data["verdict"] != "clean"
    assert "tests/test_cap.py" in summary.markdown and "tests/test_churn.py" in summary.markdown


@pytest.mark.ac("0001/AC-010")
def test_shows_mutation_score_and_missed_mutants():
    summary = render(clean_evidence(), feature_pr())
    s = signal(summary, "mutation")
    assert s["score"] == 82
    assert s["missed"] == 9
    assert "82%" in summary.markdown


@pytest.mark.ac("0001/AC-011")
@pytest.mark.parametrize(("percent", "state"), [(86.0, "clean"), (80.0, "clean"), (79.9, "not_clean")])
def test_shows_changed_line_coverage_next_to_the_minimum(percent, state):
    summary = render([quality(coverage=(percent, 80)), checks(), lock(), mutation()], feature_pr())
    s = signal(summary, "coverage")
    assert s["state"] == state
    assert s["percent"] == percent and s["minimum"] == 80
    assert "80%" in summary.markdown


@pytest.mark.ac("0001/AC-012")
@pytest.mark.parametrize("missing", ["quality", "checks", "lock", "mutation"])
def test_a_producer_without_evidence_is_not_measured(missing):
    evidence = [e for e in clean_evidence() if e["producer"] != missing]
    summary = render(evidence, feature_pr())
    names = {"quality": ["tests", "coverage"], "checks": ["tamper"], "lock": ["lock"], "mutation": ["mutation"]}
    for name in names[missing]:
        s = signal(summary, name)
        assert s["state"] == "not_measured"
        assert s["reason"]
    assert summary.data["verdict"] != "clean"
    assert "not measured" in summary.markdown


@pytest.mark.ac("0001/AC-012")
@pytest.mark.parametrize("status", ["skipped", "error"])
def test_a_skipped_or_crashed_producer_is_not_measured_with_its_reason(status):
    crashed = {**mutation(), "status": status, "reason": "mutmut exited with 2", "signals": {}}
    summary = render([quality(), checks(), lock(), crashed], feature_pr())
    s = signal(summary, "mutation")
    assert s["state"] == "not_measured"
    assert "mutmut exited with 2" in s["reason"]
    assert summary.data["verdict"] != "clean"


@pytest.mark.ac("0001/AC-012")
def test_an_unknown_evidence_version_is_not_measured():
    future = {**lock(), "schema_version": 99}
    summary = render([quality(), checks(), future, mutation()], feature_pr())
    s = signal(summary, "lock")
    assert s["state"] == "not_measured"
    assert "unknown evidence format" in s["reason"]


@pytest.mark.ac("0001/AC-012")
def test_no_evidence_at_all_is_never_clean():
    summary = render([], feature_pr())
    assert summary.data["verdict"] != "clean"
    assert all(s["state"] == "not_measured" for s in summary.data["signals"])


@pytest.mark.ac("0001/AC-013")
def test_a_chore_branch_names_the_lane_instead_of_a_criteria_table():
    ctx = Context(branch="chore/bump-ruff", target="main", title="MXAAI-50 Bump ruff", lane="chore")
    summary = render([quality(tests={}), checks(), mutation()], ctx)
    assert summary.data["lane"] == "chore"
    assert summary.data["criteria"] == []
    assert "chore" in summary.markdown
    assert "| AC" not in summary.markdown


@pytest.mark.ac("0001/AC-014")
@pytest.mark.parametrize(("lane", "branch"), [("bugfix", "bugfix/0043-null-rate"), ("hotfix", "hotfix/0044-prod")])
def test_a_bugfix_shows_its_bug_report_and_regression_test(lane, branch):
    node = "tests/test_churn.py::test_null_rate_regression"
    ctx = Context(
        branch=branch,
        target="main",
        title="MXAAI-43 Fix null churn rate",
        lane=lane,
        bug_report="specs/bug-reports/0043-null-rate.md",
        regression_tests=(node,),
    )
    summary = render([quality(tests={node: entry([])}), checks(), mutation()], ctx)
    assert summary.data["bugfix"] == {
        "bug_report": "specs/bug-reports/0043-null-rate.md",
        "tests": [{"node": node, "result": "passed"}],
    }
    assert "specs/bug-reports/0043-null-rate.md" in summary.markdown and node in summary.markdown


@pytest.mark.ac("0001/AC-019")
def test_head_takes_at_most_8_lines_even_when_every_signal_fails():
    tests = {f"tests/test_churn.py::test_{i}": entry([ac], "red", "AssertionError") for i, ac in enumerate(CRITERIA)}
    finding = {"level": "error", "message": "modifies a locked test", "path": "tests/test_churn.py", "line": None}
    evidence = [quality(tests, (10.0, 80)), checks([finding]), lock(["tests/test_churn.py"])]
    summary = render(evidence, feature_pr())
    assert len(head(summary.markdown)) <= 8, head(summary.markdown)


def many(n):
    criteria = tuple(f"0042/AC-{i:03d}" for i in range(1, n + 1))
    tests = {f"tests/test_churn.py::test_{i}": entry([ac]) for i, ac in enumerate(criteria)}
    return [quality(tests), checks(), lock(), mutation()], feature_pr(criteria=criteria)


@pytest.mark.ac("0001/AC-019")
def test_table_of_10_rows_stays_open():
    evidence, ctx = many(10)
    assert "<details" not in render(evidence, ctx).markdown


@pytest.mark.ac("0001/AC-019")
def test_table_above_10_rows_is_folded():
    evidence, ctx = many(11)
    markdown = render(evidence, ctx).markdown
    assert "<details" in markdown
    assert markdown.index("<details") < markdown.index("| 0042/AC-001")


@pytest.mark.ac("0001/AC-020")
def test_rendering_a_large_pr_takes_well_under_a_second():
    # The 60 seconds in AC-020 are measured on the pilot repo; this guards the part the summary itself adds.
    criteria = tuple(f"0042/AC-{i:03d}" for i in range(1, 41))
    tests = {f"tests/test_churn.py::test_{i}_{j}": entry([ac]) for i, ac in enumerate(criteria) for j in range(5)}
    evidence = [quality(tests), checks(), lock(), mutation()]
    start = time.perf_counter()
    render(evidence, feature_pr(criteria=criteria))
    assert time.perf_counter() - start < 1.0
