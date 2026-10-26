from pathlib import Path

import pytest

from lockstep_checks.check_ac_traceability import check_traceability
from lockstep_checks.config import load_config

TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "specs" / "_template"

SPEC = """\
## 1. Problem and outcome
## 2. Scope / non-goals
## 3. Acceptance criteria
- AC-001 THE SYSTEM SHALL score customers.
- AC-002 THE SYSTEM SHALL score them daily.
- AC-003 THE SYSTEM SHALL keep a history.
## 4. Interfaces and data contract
## 5. Test and eval plan
## 6. Risks, rollout, rollback
## 7. Open questions
"""

RESEARCH = (TEMPLATES / "design" / "research.md").read_text(encoding="utf-8")
DESIGN = (TEMPLATES / "design" / "design.md").read_text(encoding="utf-8")
DECIDED = RESEARCH.replace("Chosen: <option>, because", "Chosen: Option A, because")


def make(root: Path, state="approved", design="no", files=None, toml=None) -> Path:
    folder = root / "specs" / "0042-churn"
    folder.mkdir(parents=True)
    (folder / "spec.md").write_text(SPEC, encoding="utf-8")
    (folder / "status.yml").write_text(
        f"status: {state}\npii: no\ntrack: data\njira: MXAAI-42\ndesign: {design}\n", encoding="utf-8"
    )
    for name, text in (files or {}).items():
        (folder / name).write_text(text, encoding="utf-8")
    if toml:
        (root / "lockstep.toml").write_text(toml, encoding="utf-8")
    return root


def messages(root: Path) -> list[str]:
    return [f"{f.path}: {f.message}" for f in check_traceability(root, load_config(root), spec_only=True)]


def test_no_design_step_by_default(tmp_path):
    assert messages(make(tmp_path)) == []


def test_design_yes_needs_both_documents(tmp_path):
    found = messages(make(tmp_path, design="yes"))
    assert len(found) == 2
    assert "research.md is missing; this spec needs the research and design step (design: yes)" in found[0]
    assert found[1].startswith("specs/0042-churn/design.md: design.md is missing")


def test_draft_needs_nothing_yet(tmp_path):
    assert messages(make(tmp_path, state="draft", design="yes")) == []


def test_templates_with_a_decision_pass(tmp_path):
    assert messages(make(tmp_path, design="yes", files={"research.md": DECIDED, "design.md": DESIGN})) == []


def test_research_needs_a_decision(tmp_path):
    found = messages(make(tmp_path, design="yes", files={"research.md": RESEARCH, "design.md": DESIGN}))
    assert found == ["specs/0042-churn/research.md: section 5 names no decision: add 'Chosen: <option>, because ...'"]


def test_design_needs_sections_and_no_open_questions(tmp_path):
    design = DESIGN.replace("## 3. Data flow", "## Data flow") + "- Which warehouse?\n"
    found = messages(make(tmp_path, design="yes", files={"research.md": DECIDED, "design.md": design}))
    assert any("missing section '## 3. Data flow'" in m for m in found)
    assert any("open question must be resolved before 'approved': - Which warehouse?" in m for m in found)


@pytest.mark.parametrize("threshold, expected", [(3, 2), (4, 0), (0, 0)])
def test_criteria_threshold_from_lockstep_toml(tmp_path, threshold, expected):
    root = make(tmp_path, toml=f"[specs]\ndesign_from_criteria = {threshold}\n")
    found = messages(root)
    assert len(found) == expected
    if expected:
        assert "(3 criteria, design_from_criteria is 3)" in found[0]
