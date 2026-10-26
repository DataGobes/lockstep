"""Run with: python3 -m pytest plugins/lockstep-core/skills/self-review/tests (from the Lockstep repo root)."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCKSTEP = HERE.parents[4]
spec = importlib.util.spec_from_file_location("review_diff", HERE.parent / "scripts" / "review_diff.py")
review_diff = importlib.util.module_from_spec(spec)
sys.modules["review_diff"] = review_diff
spec.loader.exec_module(review_diff)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@example.invalid", "-c", "user.name=Test Person 001", "commit", "-qm", "x")


def make_repo(tmp_path: Path, branch_files: dict[str, str]) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    shutil.copytree(
        LOCKSTEP / "core" / "src", tmp_path / ".lockstep" / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    commit(tmp_path, {"tests/test_a.py": "def test_a():\n    assert True\n", "src/a.py": "X = 1\n"})
    git(tmp_path, "checkout", "-q", "-b", "feature/0042-churn")
    commit(tmp_path, branch_files)
    return tmp_path


BRANCH = {
    "tests/test_a.py": "def test_a():\n    assert 1\n",
    "tests/test_new.py": "def test_new():\n    assert True\n",
    "src/b.py": (
        "import json\nimport no_such_module_xyz\nfrom json import loads, no_such_name\nfrom . import sibling\n\n"
        "def f(x):\n    try:\n        return loads(x)\n    except Exception:\n        return None\n"
    ),
    "models/m.sql": "select coalesce(amount, 0) as amount, try_cast(ts as date) as d from src\n",
}


def test_reports_scope_tests_masking_and_imports(tmp_path):
    out = review_diff.review(make_repo(tmp_path, BRANCH), "main", sys.executable)
    files, protected, masking, imports = out.split("## ")[1:5]
    assert files.startswith("Changed files (4)")
    assert "tests/test_a.py (M)" in protected and "test_new" not in protected
    assert "src/b.py:9: broad except" in masking
    assert "models/m.sql:1: null replaced" in masking and "models/m.sql:1: failed cast hidden" in masking
    assert "`no_such_module_xyz`: ModuleNotFoundError" in imports
    assert "`json.no_such_name`: not found" in imports
    assert "`json`:" not in imports and "sibling" not in imports


def test_clean_branch_says_none(tmp_path):
    out = review_diff.review(
        make_repo(tmp_path, {"src/c.py": "import json\n\nY = json.dumps({})\n"}), "main", sys.executable
    )
    assert out.count("- none") == 3


def test_broken_python_command_is_reported_not_fatal(tmp_path):
    out = review_diff.review(make_repo(tmp_path, BRANCH), "main", "false")
    assert "not checked: could not run `false`" in out


SPEC = """# Churn score

## 1. Problem and outcome
## 2. Scope / non-goals
## 3. Acceptance criteria

- AC-001 WHEN a customer has no orders THE model SHALL score them 0.
- AC-002 THE model SHALL return one score per customer.

## 4. Interfaces and data contract
## 5. Test and eval plan
## 6. Risks, rollout, rollback
## 7. Open questions
"""


def test_lists_the_spec_criteria_for_the_spec_pass(tmp_path):
    root = make_repo(tmp_path, {"specs/0042-churn/spec.md": SPEC, "specs/0042-churn/status.yml": "status: approved\n"})
    out = review_diff.review(root, "main", sys.executable, "0042")
    criteria = out.split("## Criteria of spec 0042")[1]
    assert "- AC-001 WHEN a customer has no orders THE model SHALL score them 0." in criteria
    assert "- AC-002 THE model SHALL return one score per customer." in criteria
    assert "no spec 0099" in review_diff.review(root, "main", sys.executable, "0099")
