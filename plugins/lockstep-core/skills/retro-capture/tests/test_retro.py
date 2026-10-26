"""Run with: python3 -m pytest plugins/lockstep-core/skills/retro-capture/tests (from the Lockstep repo root)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("retro", HERE.parent / "scripts" / "retro.py")
retro = importlib.util.module_from_spec(spec)
sys.modules["retro"] = retro
spec.loader.exec_module(retro)


def git(root, *args, date=None):
    env = {"GIT_AUTHOR_NAME": "Test Person 001", "GIT_AUTHOR_EMAIL": "t001@example.invalid", "HOME": str(root)}
    env |= {"GIT_COMMITTER_NAME": "Test Person 001", "GIT_COMMITTER_EMAIL": "t001@example.invalid"}
    if date:
        env |= {"GIT_AUTHOR_DATE": f"{date}T12:00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00"}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def repo(tmp_path, subjects):
    git(tmp_path, "init", "-q", "-b", "main")
    for date, subject in subjects:
        git(tmp_path, "commit", "-q", "--allow-empty", "-m", subject, date=date)
    return tmp_path


def test_classify_orders_revert_before_fix():
    assert retro.classify('Revert "MXAAI-1 Fix totals"') == "revert"
    assert retro.classify("[test-change] MXAAI-2 Correct expected rounding") == "test-change"
    assert retro.classify("MXAAI-3 Fix late rows in spec 0042") == "fix"
    assert retro.classify("MXAAI-4 Add spec 0043: weekly totals") is None
    assert retro.classify("MXAAI-5 Prefix the table names") is None


def test_collects_the_range_and_reads_the_spec_id(tmp_path):
    root = repo(
        tmp_path,
        [
            ("2026-09-20", "MXAAI-1 Fix something old"),
            ("2026-10-02", "MXAAI-2 Implement spec 0042"),
            ("2026-10-05", "MXAAI-3 Fix late rows in spec 0042"),
            ("2026-10-07", 'Revert "MXAAI-2 Implement spec 0042"'),
            ("2026-10-09", "[test-change] MXAAI-4 Correct expected rounding"),
        ],
    )
    entries, total = retro.collect(retro.history(root, "main", "2026-10-01", "2026-10-31"))
    assert total == 4
    assert [(e.kind, e.spec) for e in entries] == [("test-change", None), ("revert", "0042"), ("fix", "0042")]


def test_json_output(tmp_path, capsys):
    root = repo(tmp_path, [("2026-10-05", 'Revert "MXAAI-2 Add totals"')])
    assert retro.main(["--root", str(root), "--ref", "main", "--since", "2026-10-01", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["commits"] == 1
    assert out["entries"][0]["kind"] == "revert"


def test_bad_ref_fails_cleanly(tmp_path, capsys):
    root = repo(tmp_path, [("2026-10-05", "MXAAI-1 Start")])
    assert retro.main(["--root", str(root), "--ref", "nope", "--since", "2026-10-01"]) == 1
    assert "git log failed" in capsys.readouterr().err
