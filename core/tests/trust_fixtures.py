"""Evidence files and PR contexts for the trust summary tests (spec 0001). Invented values only."""

from lockstep_checks.trust_summary import Context

SPEC = "0042"
CRITERIA = ("0042/AC-001", "0042/AC-002", "0042/AC-003")


def entry(acs, result="passes", detail=""):
    return {"acs": list(acs), "result": result, "detail": detail}


def quality(tests=None, coverage=(86.0, 80)):
    signals = {
        "tests": tests
        if tests is not None
        else {
            "tests/test_churn.py::test_rate": entry(["0042/AC-001"]),
            "tests/test_churn.py::test_empty": entry(["0042/AC-002"]),
            "tests/test_churn.py::test_cap": entry(["0042/AC-003"]),
        }
    }
    if coverage is not None:
        signals["coverage_changed_lines"] = {"percent": coverage[0], "minimum": coverage[1]}
    return {"schema_version": 1, "producer": "quality", "status": "measured", "reason": None, "signals": signals}


def checks(tamper_findings=(), test_change=False):
    return {
        "schema_version": 1,
        "producer": "checks",
        "status": "measured",
        "reason": None,
        "signals": {
            "checks": {
                "test_tamper": {"mode": "enforce", "test_change": test_change, "findings": list(tamper_findings)},
            }
        },
    }


def lock(changed_since=()):
    return {
        "schema_version": 1,
        "producer": "lock",
        "status": "measured",
        "reason": None,
        "signals": {
            "lock": {
                "commit": "3f2a9c1d8e7b6a5f4e3d2c1b0a9f8e7d6c5b4a39",
                "date": "2026-10-20",
                "changed_since": list(changed_since),
            }
        },
    }


def mutation(caught=41, total=50, survived=7, no_tests=2):
    return {
        "schema_version": 1,
        "producer": "mutation",
        "status": "measured",
        "reason": None,
        "signals": {"mutation": {"caught": caught, "total": total, "survived": survived, "no_tests": no_tests}},
    }


def clean_evidence():
    return [quality(), checks(), lock(), mutation()]


def feature_pr(**kw):
    """A PR from the feature branch into main: the full gate, nothing excused."""
    base = {"branch": "feature/0042-churn", "target": "main", "title": "MXAAI-42 Churn rate", "spec_id": SPEC}
    base["criteria"] = CRITERIA
    base.update(kw)
    return Context(**base)


def into_feature_branch(**kw):
    """The spec-and-tests PR: test/0042-churn into feature/0042-churn, the spec's new tests red on purpose."""
    base = {
        "branch": "test/0042-churn",
        "target": "feature/0042-churn",
        "title": "MXAAI-42 Add failing tests for spec 0042",
        "spec_id": SPEC,
        "criteria": CRITERIA,
        "expected_red": ("tests/test_churn.py",),
    }
    base.update(kw)
    return Context(**base)


def signal(summary, name):
    found = [s for s in summary.data["signals"] if s["name"] == name]
    assert len(found) == 1, f"expected one {name!r} signal in {summary.data['signals']}"
    return found[0]


def head(markdown):
    """The lines above the criteria table: the headline and the signal lines."""
    lines = []
    for line in markdown.splitlines():
        if line.startswith(("|", "<details")):
            break
        if line.strip() and not line.startswith("<!--"):
            lines.append(line)
    return lines
