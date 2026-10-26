"""Run with: python3 -m pytest plugins/lockstep-core/skills/tests-first/tests (from the Lockstep repo root)."""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("red_report", HERE.parent / "scripts" / "red_report.py")
red_report = importlib.util.module_from_spec(spec)
sys.modules["red_report"] = red_report
spec.loader.exec_module(red_report)

SPEC = """\
# Churn
## 1. Problem and outcome
x
## 2. Scope / non-goals
x
## 3. Acceptance criteria
- AC-001 THE scorer SHALL return a score between 0 and 1.
- AC-002 WHEN the input is empty THE scorer SHALL return an empty list.
- AC-003 THE scorer SHALL log the row count.
## 4. Interfaces and data contract
x
## 5. Test and eval plan
x
## 6. Risks, rollout, rollback
x
## 7. Open questions
"""
STATUS = "status: approved\npii: no\ntrack: ai\njira: MXAAI-42\n"
STUB = "def score(rows):\n    raise NotImplementedError\n"
CONFTEST = 'def pytest_configure(config):\n    config.addinivalue_line("markers", "ac(id): criterion")\n'


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    shutil.copytree(
        LOCKSTEP / "core" / "src", tmp_path / ".lockstep" / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    write(
        tmp_path,
        {
            "specs/0042-churn/spec.md": SPEC,
            "specs/0042-churn/status.yml": STATUS,
            "src/churn.py": STUB,
            "conftest.py": CONFTEST
            + "import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).parent / 'src'))\n",
        },
    )
    return tmp_path


def report(repo):
    criteria = red_report.spec_criteria(repo, "0042")
    tests = red_report.run_pytest(repo, f"{sys.executable} -m pytest", ["tests"])
    rows, ok = red_report.evaluate(criteria, tests)
    return {(ac, result) for ac, _, result, _ in rows}, ok


# Written as @MARK so the repo's own traceability check does not read these as real test references.
GOOD = """\
import pytest
from churn import score

@MARK("0042/AC-001")
def test_score_in_range():
    assert 0 <= score([{"id": 1}])[0] <= 1

@MARK("0042/AC-002")
def test_empty_input():
    assert score([]) == []

@MARK("0042/AC-003")
def test_logs_row_count(caplog):
    score([{"id": 1}])
    assert "1 rows" in caplog.text
""".replace("@MARK", "@pytest.mark.ac")


def test_all_red_for_the_right_reason(repo):
    write(repo, {"tests/test_churn.py": GOOD})
    rows, ok = report(repo)
    assert ok
    assert rows == {("0042/AC-001", "red"), ("0042/AC-002", "red"), ("0042/AC-003", "red")}


def test_passing_test_and_missing_criterion_are_problems(repo):
    write(
        repo,
        {
            "src/churn.py": "def score(rows):\n    return []\n",
            "tests/test_churn.py": GOOD.split('@pytest.mark.ac("0042/AC-003")')[0],
        },
    )
    rows, ok = report(repo)
    assert not ok
    assert ("0042/AC-002", "passes") in rows
    assert ("0042/AC-003", "no test") in rows


def test_import_errors_are_the_wrong_reason(repo):
    write(repo, {"tests/test_churn.py": GOOD.replace("from churn import score", "from churn_v2 import score")})
    rows, ok = report(repo)
    assert not ok
    assert ("-", "collection-error") in rows


def test_calling_a_missing_function_is_the_wrong_reason(repo):
    write(
        repo,
        {
            "tests/test_churn.py": GOOD.replace("from churn import score", "import churn").replace(
                "score(", "churn.scores("
            )
        },
    )
    rows, ok = report(repo)
    assert not ok
    assert ("0042/AC-001", "wrong-reason") in rows


def test_unknown_criterion_is_reported(repo):
    write(
        repo,
        {"tests/test_churn.py": GOOD + "\n@" + 'pytest.mark.ac("0042/AC-009")\ndef test_extra():\n    assert False\n'},
    )
    rows, ok = report(repo)
    assert not ok
    assert ("0042/AC-009", "unknown criterion") in rows


def test_unknown_spec_exits(repo):
    with pytest.raises(SystemExit, match="no spec 0099"):
        red_report.spec_criteria(repo, "0099")


def test_green_after_implementation(repo):
    impl = (
        "import logging\n\ndef score(rows):\n    logging.getLogger(__name__).warning('%d rows', len(rows))\n"
        "    return [0.5 for _ in rows]\n"
    )
    write(repo, {"src/churn.py": impl, "tests/test_churn.py": GOOD})
    tests = red_report.run_pytest(repo, f"{sys.executable} -m pytest", ["tests"])
    criteria = red_report.spec_criteria(repo, "0042")
    assert red_report.evaluate(criteria, tests, "green")[1]
    assert not red_report.evaluate(criteria, tests, "red")[1]
