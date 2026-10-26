"""Run with: python3 -m pytest plugins/lockstep-ai/skills/eval-case/tests (from the Lockstep repo root)."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("check_cases", HERE.parent / "scripts" / "check_cases.py")
check_cases = importlib.util.module_from_spec(spec)
sys.modules["check_cases"] = check_cases
spec.loader.exec_module(check_cases)

SPEC = "# s\n## 1. P\n## 2. S\n## 3. Acceptance criteria\n- AC-001 THE bot SHALL answer.\n## 4. I\n## 5. T\n## 6. R\n## 7. O\n"


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(
        LOCKSTEP / "core" / "src", tmp_path / ".lockstep" / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    d = tmp_path / "specs" / "0042-bot"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(SPEC, encoding="utf-8")
    (d / "status.yml").write_text("status: approved\npii: no\ntrack: ai\njira: MXAAI-42\n", encoding="utf-8")
    return tmp_path


def case(**over):
    base = {
        "id": "c1",
        "ac": "0042/AC-001",
        "inputs": {"question": "When does order 1001 arrive?"},
        "expectations": {"expected_facts": ["delivery date"]},
    }
    return {**base, **over}


def run(repo, cases, name="cases.jsonl"):
    path = repo / "evals" / "datasets" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    return check_cases.check([path], check_cases.criteria(repo))


def test_good_case_passes(repo):
    assert run(repo, [case(), case(id="c2", inputs={"question": "Asked on 2026-10-26 10:30 by Test Person 001"})]) == []


@pytest.mark.parametrize(
    "over, fragment",
    [
        ({"ac": "AC-001"}, "ac must name a criterion"),
        ({"ac": "0042/AC-009"}, "not a criterion of any spec"),
        ({"expectations": {}}, "expectations is empty"),
        ({"inputs": {"question": "Mail first.last@gmail.com"}}, "email address"),
        ({"inputs": {"question": "Call +31 6 1234 5678"}}, "phone number"),
        ({"inputs": {"question": "Refund to NL91 ABNA 0417 1643 00"}}, "IBAN"),
    ],
)
def test_bad_cases_fail(repo, over, fragment):
    problems = run(repo, [case(**over)])
    assert any(fragment in p for p in problems), problems


def test_invented_email_domains_are_fine(repo):
    assert run(repo, [case(inputs={"question": "Mail test.person.001@example.com"})]) == []


def test_duplicate_ids(repo):
    assert any("also used at" in p for p in run(repo, [case(), case()]))


def test_csv_rows(repo):
    path = repo / "evals" / "datasets" / "cases.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        'id,ac,inputs,expectations\nc1,0042/AC-001,"{""question"": ""Hi""}","{""expected_response"": ""Hello""}"\n',
        encoding="utf-8",
    )
    assert check_cases.check([path], check_cases.criteria(repo)) == []
