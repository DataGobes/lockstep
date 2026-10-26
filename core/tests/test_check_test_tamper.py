from pathlib import Path

from lockstep_checks.check_test_tamper import _run, check_test_tamper
from lockstep_checks.cli import run
from lockstep_checks.config import load_config
from lockstep_checks.gitdiff import ChangedFile

CFG = load_config(Path("/no-such-dir"))


def changed(path, status="M", lines=(), old_path=None):
    return ChangedFile(path, status, old_path, added_lines=tuple(enumerate(lines, start=1)))


def errors(findings):
    return [f for f in findings if f.level == "error"]


def test_new_test_file_is_allowed():
    assert check_test_tamper([changed("tests/test_new.py", "A", ["def test_x(): assert f() == 1"])], CFG, "t") == []


def test_source_change_is_allowed():
    assert check_test_tamper([changed("src/app.py", "M", ["x = 1"])], CFG, "t") == []


def test_modifying_existing_test_fails_and_names_file():
    found = errors(check_test_tamper([changed("tests/test_a.py")], CFG, "MXAAI-1 x"))
    assert found[0].path == "tests/test_a.py"
    assert "modifies" in found[0].message
    assert "[test-change]" in found[-1].message


def test_deleting_or_renaming_protected_files_fails():
    files = [
        changed("dbt/models/_dim.unit_tests.yml", "D"),
        changed("tests/renamed.py", "R", old_path="tests/test_a.py"),
        changed("evals/thresholds.yml"),
        changed("evals/datasets/golden.jsonl"),
        changed("src/__snapshots__/x.ambr"),
    ]
    paths = [f.path for f in errors(check_test_tamper(files, CFG, "t")) if f.path]
    assert paths == [
        "dbt/models/_dim.unit_tests.yml",
        "tests/test_a.py",
        "evals/thresholds.yml",
        "evals/datasets/golden.jsonl",
        "src/__snapshots__/x.ambr",
    ]


def test_moving_a_file_into_tests_is_allowed():
    assert check_test_tamper([changed("tests/helpers.py", "R", old_path="src/helpers.py")], CFG, "t") == []


def test_weakening_lines_fail_anywhere_with_line_number():
    cases = [
        ("tests/test_new.py", "A", "@pytest.mark.skip(reason='flaky')"),
        ("tests/test_new.py", "A", "    pytest.xfail('later')"),
        ("src/app.py", "M", "import os  # noqa: F401"),
        ("src/app.py", "M", "x: int = 'a'  # type: ignore"),
        ("dbt/models/_x.yml", "M", "      enabled: false"),
        ("dbt/models/_x.yml", "M", "    - severity: warn"),
        ("dbt/tests/assert_x.sql", "A", "{{ config(severity='warn') }}"),
    ]
    for path, status, line in cases:
        found = errors(check_test_tamper([changed(path, status, ["ok = 1", line])], CFG, "t"))
        assert found and found[0].path == path and found[0].line == 2, line


def test_harmless_lookalikes_pass():
    lines = ["# we never skip tests here", "severity_level = 'warning'", "enabled = True"]
    assert check_test_tamper([changed("src/app.py", "M", lines)], CFG, "t") == []


def test_test_change_title_downgrades_to_warnings():
    findings = check_test_tamper([changed("tests/test_a.py")], CFG, "[test-change] MXAAI-1 fix wrong expectation")
    assert findings and all(f.level == "warning" for f in findings)


def test_test_change_tag_must_lead_the_title():
    assert errors(check_test_tamper([changed("tests/test_a.py")], CFG, "MXAAI-1 [test-change] x"))


def test_end_to_end(repo, capsys):
    repo.commit({"tests/test_a.py": "def test_a():\n    assert 1\n"})
    repo.branch("feature/0042-x")
    repo.commit({"tests/test_a.py": "def test_a():\n    assert True\n", "tests/test_b.py": "def test_b(): ...\n"})
    code = run("check_test_tamper", "", _run, ["--root", str(repo.root), "--base", "main", "--title", "MXAAI-1 x"])
    out = capsys.readouterr().out
    assert code == 1
    assert "tests/test_a.py" in out and "tests/test_b.py" not in out


def test_warn_mode_passes_and_says_it_would_block(repo, capsys):
    repo.commit(
        {"tests/test_a.py": "def test_a():\n    assert 1\n", "lockstep.toml": '[enforcement]\ndefault = "warn"\n'}
    )
    repo.branch("feature/0042-x")
    repo.commit({"tests/test_a.py": "def test_a():\n    assert True\n"})
    code = run("check_test_tamper", "", _run, ["--root", str(repo.root), "--base", "main", "--title", "MXAAI-1 x"])
    out = capsys.readouterr().out
    assert code == 0
    assert "WARNING check_test_tamper: tests/test_a.py: would block (warn mode): modifies" in out


def test_broken_config_fails_even_in_warn_mode(repo, capsys):
    repo.commit({"lockstep.toml": '[enforcement]\ndefault = "warn"\nwarn_lines = 1\n'})
    code = run("check_test_tamper", "", _run, ["--root", str(repo.root), "--base", "main"])
    assert code == 1
    assert "enforcement.warn_lines" in capsys.readouterr().out


def tagged(path, lines, deleted=0):
    return ChangedFile(path, "M", None, len(lines), deleted, tuple(enumerate(lines, start=1)))


ADOPT = [
    tagged("tests/test_prices.py", ["import pytest", "", '@pytest.mark.ac("0042/AC-001", "0042/AC-002")']),
    tagged("tests/test_vat.py", ['pytestmark = [pytest.mark.ac("0042/AC-003")]']),
    tagged("models/_prices.unit_tests.yml", ["      meta: {ac: 0042/AC-004}"]),
]


def test_baseline_branch_may_tag_existing_tests():
    assert check_test_tamper(ADOPT, CFG, "MXAAI-1 Pin prices", branch="baseline/0042-prices") == []


def test_tagging_existing_tests_elsewhere_still_fails():
    found = errors(check_test_tamper(ADOPT[:1], CFG, "MXAAI-1 x", branch="feature/0042-prices"))
    assert found[0].path == "tests/test_prices.py"


def test_baseline_branch_fails_any_other_edit_to_an_existing_test():
    files = [
        tagged("tests/test_a.py", ['@pytest.mark.ac("0042/AC-001")', "    assert price(1) == 2"]),
        tagged("tests/test_b.py", ['@pytest.mark.ac("0042/AC-001")'], deleted=1),
        tagged("tests/test_c.py", ["import pytest"]),
        tagged("tests/test_d.py", ['@pytest.mark.ac("AC-001")']),
        ChangedFile("tests/test_e.py", "D"),
    ]
    paths = [f.path for f in errors(check_test_tamper(files, CFG, "MXAAI-1 x", branch="baseline/0042-a")) if f.path]
    assert paths == ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py", "tests/test_d.py", "tests/test_e.py"]


def test_baseline_tags_still_cannot_skip_a_test():
    files = [tagged("tests/test_a.py", ['@pytest.mark.ac("0042/AC-001")', "@pytest.mark.skip"])]
    found = errors(check_test_tamper(files, CFG, "MXAAI-1 x", branch="baseline/0042-a"))
    assert any("skips or xfails" in f.message for f in found)
