import io

from lockstep_checks.report import Finding, emit


def test_local_output_and_exit_code():
    out = io.StringIO()
    code = emit([Finding("warning", "big"), Finding("error", "bad", "tests/a.py", 3)], "check_x", env={}, out=out)
    assert code == 1
    assert out.getvalue().splitlines() == ["WARNING check_x: big", "ERROR check_x: tests/a.py:3: bad"]


def test_pipeline_output_uses_logging_commands():
    out = io.StringIO()
    code = emit([Finding("error", "bad\nline", "tests/a.py", 3)], "check_x", env={"TF_BUILD": "True"}, out=out)
    assert code == 1
    assert out.getvalue() == "##vso[task.logissue type=error;sourcepath=tests/a.py;linenumber=3]check_x: bad%0Aline\n"


def test_warnings_only_pass():
    out = io.StringIO()
    assert emit([Finding("warning", "big")], "check_x", env={}, out=out) == 0


def test_no_findings_says_ok():
    out = io.StringIO()
    assert emit([], "check_x", env={}, out=out) == 0
    assert out.getvalue() == "check_x: OK\n"
