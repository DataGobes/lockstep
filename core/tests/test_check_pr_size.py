from pathlib import Path

from lockstep_checks.check_pr_size import _run, check_pr_size
from lockstep_checks.cli import run
from lockstep_checks.config import load_config
from lockstep_checks.gitdiff import ChangedFile

CFG = load_config(Path("/no-such-dir"))


def files(*sizes: int, path="src/f{}.py") -> list[ChangedFile]:
    return [ChangedFile(path.format(i), "M", added=n, deleted=0) for i, n in enumerate(sizes)]


def levels(findings):
    return [f.level for f in findings]


def test_small_pr_passes():
    assert check_pr_size(files(100, 200), CFG, "MXAAI-1 x") == []


def test_warns_above_400():
    assert levels(check_pr_size(files(401), CFG, "t")) == ["warning"]


def test_fails_above_800_unless_approved():
    assert levels(check_pr_size(files(801), CFG, "MXAAI-1 x")) == ["error"]
    assert levels(check_pr_size(files(801), CFG, "MXAAI-1 x [large-approved]")) == ["warning"]


def test_generated_files_do_not_count():
    generated = [
        ChangedFile("uv.lock", "M", added=5000, deleted=0),
        ChangedFile("dbt/target/manifest.json", "M", added=9000),
    ]
    assert check_pr_size(files(10) + generated, CFG, "t") == []


def test_binary_files_count_as_zero_lines():
    assert check_pr_size([ChangedFile("img.png", "A", added=None, deleted=None)], CFG, "t") == []


def test_more_than_100_files_always_fails():
    findings = check_pr_size(files(*[1] * 101), CFG, "[large-approved]")
    assert levels(findings) == ["error"]
    assert "101 files" in findings[0].message


def test_end_to_end(repo, capsys):
    repo.commit({"a.py": "x\n"})
    repo.branch("feature/0042-x")
    repo.commit({"a.py": "y\n" * 900})
    code = run("check_pr_size", "", _run, ["--root", str(repo.root), "--base", "main", "--title", "MXAAI-1 x"])
    assert code == 1
    assert "901 changed lines" in capsys.readouterr().out
