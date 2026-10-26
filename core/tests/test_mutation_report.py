import sys
from pathlib import Path

from lockstep_checks.mutation_report import (
    Mutant,
    changed_modules,
    findings_for,
    locate,
    module_name,
    parse_results,
    patterns_for,
    report,
    summarize,
)

RESULTS = """
    calc.ops.x_add__mutmut_1: killed
    calc.ops.x_clamp__mutmut_1: survived
    calc.ops.x_clamp__mutmut_2: no tests
    calc.ops.xǁBoxǁsize__mutmut_1: timeout
    calc.other.x_mul__mutmut_1: not checked
    calc.x_root__mutmut_1: survived
"""

OPS = "def add(a, b):\n    return a + b\n\n\ndef clamp(x, lo, hi):\n    if x < lo:\n        return lo\n    return x\n"

SHOW = """# calc.ops.x_clamp__mutmut_1: survived
--- src/calc/ops.py
+++ src/calc/ops.py
@@ -1,4 +1,4 @@
 def clamp(x, lo, hi):
-    if x < lo:
+    if x <= lo:
         return lo
     return x
"""


def test_module_names_follow_mutmut():
    assert module_name("src/calc/ops.py") == "calc.ops"
    assert module_name("src/calc/__init__.py") == "calc"
    assert module_name("pkg/mod.py") == "pkg.mod"


def test_only_changed_source_modules_are_mutated():
    paths = ["src/calc/ops.py", "src/calc/test_ops.py", "tests/test_ops.py", "src/calc/data.json", "README.md"]
    assert changed_modules(paths, "src") == ["calc.ops"]
    assert changed_modules(["src/calc/__init__.py"], "src/") == ["calc"]


def test_package_pattern_does_not_pull_in_submodules():
    names = [m.name for m in parse_results(RESULTS, patterns_for(["calc"]))]
    assert names == ["calc.x_root__mutmut_1"]


def test_parse_results_keeps_matching_mutants_with_their_status():
    mutants = parse_results(RESULTS, patterns_for(["calc.ops"]))
    assert [(m.name.split(".")[-1], m.status) for m in mutants] == [
        ("x_add__mutmut_1", "killed"),
        ("x_clamp__mutmut_1", "survived"),
        ("x_clamp__mutmut_2", "no tests"),
        ("xǁBoxǁsize__mutmut_1", "timeout"),
    ]
    assert len(parse_results(RESULTS, None)) == 6


def test_score_counts_timeouts_as_caught_and_untested_as_missed():
    summary = summarize(parse_results(RESULTS, patterns_for(["calc.ops"])))
    assert summary == "mutation score 50%: 2 of 4 mutants caught (1 no tests, 1 survived)"
    assert summarize([Mutant("a", "not checked")]).startswith("no mutants tested")


def test_locate_finds_the_line_in_the_file_not_in_the_function(tmp_path):
    (tmp_path / "src/calc").mkdir(parents=True)
    (tmp_path / "src/calc/ops.py").write_text(OPS)
    m = locate(Mutant("calc.ops.x_clamp__mutmut_1", "survived"), SHOW, tmp_path)
    assert (m.path, m.line, m.change) == ("src/calc/ops.py", 6, "if x < lo: -> if x <= lo:")


def test_locate_keeps_the_path_when_the_function_moved(tmp_path):
    m = locate(Mutant("n", "survived"), SHOW, tmp_path)
    assert (m.path, m.line) == ("src/calc/ops.py", None)
    assert locate(Mutant("n", "survived"), "", tmp_path) == Mutant("n", "survived")


def test_findings_are_warnings_and_capped():
    mutants = [Mutant(f"m{i}", "survived", "src/a.py", i) for i in range(5)]
    findings = findings_for(mutants, "score", max_listed=2)
    assert {f.level for f in findings} == {"warning"}
    assert [f.line for f in findings] == [None, 0, 1, None]
    assert "3 more missed mutants" in findings[-1].message


FAKE_MUTMUT = """
import sys
cmd = sys.argv[1]
if cmd == "run":
    open("ran.txt", "w").write(" ".join(sys.argv[2:]))
    sys.exit(int(open("run_exit").read()) if __import__("os").path.exists("run_exit") else 0)
if cmd == "results":
    print('''RESULTS''')
if cmd == "show":
    print('''SHOW''')
""".replace("RESULTS", RESULTS).replace("SHOW", SHOW)


def fake_mutmut(root: Path) -> list[str]:
    script = root.parent / "fake_mutmut.py"
    script.write_text(FAKE_MUTMUT, encoding="utf-8")
    return [sys.executable, str(script)]


def test_report_mutates_changed_modules_and_never_fails(repo, capsys):
    repo.commit({"src/calc/ops.py": OPS, "src/calc/other.py": "x = 1\n"})
    repo.branch("feature/0042-x")
    repo.commit({"src/calc/ops.py": OPS + "\n# changed\n"})
    (repo.root / "run_exit").write_text("1")
    assert report(repo.root, "main", "src", fake_mutmut(repo.root), False, 20) == 0
    assert (repo.root / "ran.txt").read_text() == "calc.ops.x_* calc.ops.xǁ*"
    out = capsys.readouterr().out
    assert "mutmut run exited 1" in out
    assert "mutation score 50%" in out
    assert "src/calc/ops.py:6: mutant survived: if x < lo: -> if x <= lo:" in out
    assert "ERROR" not in out


def test_report_without_changed_modules_runs_nothing(repo, capsys):
    repo.commit({"src/calc/ops.py": OPS})
    repo.branch("feature/0042-x")
    repo.commit({"README.md": "docs\n"})
    assert report(repo.root, "main", "src", fake_mutmut(repo.root), False, 20) == 0
    assert not (repo.root / "ran.txt").exists()
    assert "nothing to mutate" in capsys.readouterr().out


def test_report_all_mutates_everything(repo, capsys):
    repo.commit({"src/calc/ops.py": OPS})
    assert report(repo.root, "main", "src", fake_mutmut(repo.root), True, 20) == 0
    assert (repo.root / "ran.txt").read_text() == ""
    assert "mutation score 40%: 2 of 5" in capsys.readouterr().out


def test_report_warns_when_mutmut_is_missing_or_base_unknown(repo, capsys):
    repo.commit({"src/calc/ops.py": OPS})
    assert report(repo.root, "main", "src", ["no-such-mutmut-command"], True, 20) == 0
    assert report(repo.root, "origin/nope", "src", ["mutmut"], False, 20) == 0
    out = capsys.readouterr().out
    assert "cannot run mutmut" in out and "cannot read the PR's changes" in out
