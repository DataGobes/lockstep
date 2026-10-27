import io

from lockstep_checks.report import Finding, apply_mode, emit


def test_local_output_and_exit_code():
    out = io.StringIO()
    code = emit([Finding("warning", "big"), Finding("error", "bad", "tests/a.py", 3)], "check_x", env={}, out=out)
    assert code == 1
    assert out.getvalue().splitlines() == ["WARNING check_x: big", "ERROR check_x: tests/a.py:3: bad"]


def test_pipeline_output_uses_logging_commands():
    out = io.StringIO()
    code = emit([Finding("error", "bad\nline", "tests/a.py", 3)], "check_x", env={"TF_BUILD": "True"}, out=out)
    assert code == 1
    assert out.getvalue().splitlines()[0] == (
        "##vso[task.logissue type=error;sourcepath=tests/a.py;linenumber=3]check_x: bad%0Aline"
    )


def test_warnings_only_pass():
    out = io.StringIO()
    assert emit([Finding("warning", "big")], "check_x", env={}, out=out) == 0


def test_no_findings_says_ok():
    out = io.StringIO()
    assert emit([], "check_x", env={}, out=out) == 0
    assert out.getvalue() == "check_x: OK\n"


def test_warn_mode_downgrades_errors_only():
    findings = apply_mode([Finding("error", "bad", "a.py"), Finding("warning", "big")], "warn")
    assert [(f.level, f.message, f.would_block) for f in findings] == [
        ("warning", "would block (warn mode): bad", True),
        ("warning", "big", False),
    ]
    assert emit(findings, "check_x", env={}, out=io.StringIO()) == 0


def test_enforce_mode_keeps_errors():
    findings = [Finding("error", "bad")]
    assert apply_mode(findings, "enforce") == findings


def test_pipeline_tags_the_run_so_the_team_can_count():
    out = io.StringIO()
    emit(apply_mode([Finding("error", "bad")], "warn"), "check_x", env={"TF_BUILD": "True"}, out=out)
    assert "##vso[build.addbuildtag]lockstep-would-block-x" in out.getvalue()
    out = io.StringIO()
    emit([Finding("error", "bad")], "check_x", env={"TF_BUILD": "True"}, out=out)
    assert "##vso[build.addbuildtag]lockstep-blocked-x" in out.getvalue()
    out = io.StringIO()
    emit([Finding("warning", "big")], "check_x", env={"TF_BUILD": "True"}, out=out)
    assert "addbuildtag" not in out.getvalue()


GITHUB = {"GITHUB_ACTIONS": "true"}


def test_github_output_uses_annotations():
    out = io.StringIO()
    code = emit([Finding("error", "bad\nline 100%", "tests/a,b.py", 3)], "check_x", env=GITHUB, out=out)
    assert code == 1
    assert (
        out.getvalue().splitlines()[0] == "::error file=tests/a%2Cb.py,line=3,title=lockstep check_x::bad%0Aline 100%25"
    )


def test_github_annotation_without_a_file():
    out = io.StringIO()
    emit([Finding("warning", "big")], "check_x", env=GITHUB, out=out)
    assert out.getvalue().splitlines()[0] == "::warning title=lockstep check_x::big"


def test_github_marks_blocked_and_would_block_with_a_notice():
    out = io.StringIO()
    emit([Finding("error", "bad")], "check_x", env=GITHUB, out=out)
    assert "::notice title=lockstep-blocked-x::check_x fired" in out.getvalue()
    out = io.StringIO()
    emit(apply_mode([Finding("error", "bad")], "warn"), "check_x", env=GITHUB, out=out)
    assert "::notice title=lockstep-would-block-x::check_x fired" in out.getvalue()
    assert "lockstep-blocked-x" not in out.getvalue()
