"""Regression test for specs/bug-reports/evidence-artifact-names.md: each PR template publishes its evidence under its
own fixed artifact name, so two jobs in one run never collide and the summary downloads every producer's evidence."""

import re
from pathlib import Path

import pytest

PIPELINES = Path(__file__).resolve().parents[1] / "pipelines"


def evidence_artifacts() -> dict[str, str]:
    found = {}
    for path in sorted(PIPELINES.glob("*.yml")):
        names = re.findall(r"^\s*artifact: (lockstep-evidence-\S*)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if names:
            assert len(names) == 1, f"{path.name} publishes evidence more than once"
            found[path.name] = names[0]
    return found


@pytest.mark.ac("0001/AC-006")
def test_each_pr_template_publishes_evidence_under_its_own_fixed_name():
    assert evidence_artifacts() == {
        "lockstep-pr.yml": "lockstep-evidence-checks",
        "mutation-report.yml": "lockstep-evidence-mutation",
        "python-quality.yml": "lockstep-evidence-quality",
    }


@pytest.mark.ac("0001/AC-006")
def test_the_summary_downloads_every_evidence_artifact():
    summary = (PIPELINES / "trust-summary.yml").read_text(encoding="utf-8")
    assert "itemPattern: lockstep-evidence-*/**" in summary
