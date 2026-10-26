from pathlib import Path

import pytest

from lockstep_checks.check_ac_traceability import check_traceability, main
from lockstep_checks.config import load_config
from lockstep_checks.specdoc import parse_spec

TEMPLATE = (Path(__file__).resolve().parents[2] / "templates" / "specs" / "_template" / "spec.md").read_text()

SPEC = """\
## 1. Problem and outcome
x
## 2. Scope / non-goals
x
## 3. Acceptance criteria
- AC-001 WHEN a churn score is requested THE SYSTEM SHALL return it.
- ~~AC-002~~ superseded by AC-003
- AC-003 THE pipeline SHALL finish in 15 min.
## 4. Interfaces and data contract
## 5. Test and eval plan
## 6. Risks, rollout, rollback
## 7. Open questions
{questions}"""


def status(state: str) -> str:
    commit = "locked_at_commit: abc1234\n" if state in ("tests-locked", "implemented") else ""
    return f"status: {state}\npii: no\ntrack: data\njira: MXAAI-42\n{commit}"


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def spec_files(spec_id="0042", state="tests-locked", questions="") -> dict[str, str]:
    return {
        f"specs/{spec_id}-churn/spec.md": SPEC.format(questions=questions),
        f"specs/{spec_id}-churn/status.yml": status(state),
    }


def messages(findings, level="error"):
    return [f"{f.path}:{f.line}: {f.message}" if f.path else f.message for f in findings if f.level == level]


def check(root, spec_only=False):
    return check_traceability(root, load_config(root), spec_only)


def test_template_spec_lints_clean():
    doc = parse_spec(TEMPLATE)
    assert doc.problems == []
    assert list(doc.criteria) == ["AC-001", "AC-002", "AC-003"]


GWT = """\
## 3. Acceptance criteria
- AC-001 Refund above the limit waits for approval
  - GIVEN a refund of 600 EUR and an approval limit of 500 EUR
  - WHEN the agent submits it
  - THEN it waits for a manager's approval
  - AND the customer is not paid yet
- AC-002 WHEN a refund is approved THE SYSTEM SHALL pay it within one day.
"""


def ac_problems(text: str, ac_format: str = "any") -> list[str]:
    return [msg for _, msg in parse_spec(text, ac_format).problems if msg.startswith("AC-")]


def test_given_when_then_criterion_keeps_its_steps():
    doc = parse_spec(GWT)
    assert doc.text["AC-001"][0] == "- AC-001 Refund above the limit waits for approval"
    assert doc.text["AC-001"][1:] == [
        "- GIVEN a refund of 600 EUR and an approval limit of 500 EUR",
        "- WHEN the agent submits it",
        "- THEN it waits for a manager's approval",
        "- AND the customer is not paid yet",
    ]
    assert doc.text["AC-002"] == ["- AC-002 WHEN a refund is approved THE SYSTEM SHALL pay it within one day."]


def test_any_format_accepts_both_styles():
    assert ac_problems(GWT) == []


def test_ears_format_rejects_steps_and_sentences_without_shall():
    assert ac_problems(GWT, "ears") == [
        "AC-001 has Given/When/Then steps; this repo writes criteria in EARS (ac_format = 'ears')"
    ]
    assert ac_problems("## 3. A\n- AC-001 the system returns a score\n", "ears") == [
        "AC-001 is not EARS: it needs '... THE <system> SHALL <behaviour>'"
    ]


def test_given_when_then_format_needs_steps():
    assert ac_problems(GWT, "given-when-then") == [
        "AC-002 needs Given/When/Then steps under it (ac_format = 'given-when-then')"
    ]


@pytest.mark.parametrize(
    "steps, problem",
    [
        (["WHEN x", "THEN y"], None),  # GIVEN is optional
        (["**Given** x", "**When** y", "**Then** z", "But w"], None),  # bold and any case
        (["GIVEN x", "AND y", "WHEN z", "THEN w"], None),
        (["THEN x", "WHEN y"], "out of order"),
        (["GIVEN x", "THEN y", "AND z", "WHEN w"], "out of order"),
        (["AND x", "WHEN y", "THEN z"], "starts with AND"),
        (["GIVEN x", "WHEN y"], "has no THEN step"),
        (["GIVEN x"], "has no WHEN or THEN step"),
    ],
)
def test_step_order(steps, problem):
    text = "## 3. A\n- AC-001 title\n" + "".join(f"  - {s}\n" for s in steps)
    found = ac_problems(text)
    assert (found == []) if problem is None else (len(found) == 1 and problem in found[0])


def test_steps_end_at_the_next_unindented_line():
    text = "## 3. A\n- AC-001 title\n  - WHEN x\n\n  - THEN y\n\nNever renumber.\n  - GIVEN z\n"
    assert parse_spec(text).text["AC-001"] == ["- AC-001 title", "- WHEN x", "- THEN y"]


def test_ac_format_comes_from_lockstep_toml(tmp_path):
    write(tmp_path, spec_files())
    (tmp_path / "lockstep.toml").write_text('[specs]\nac_format = "given-when-then"\n')
    messages = [f.message for f in check(tmp_path, spec_only=True)]
    assert any("AC-001 needs Given/When/Then steps" in m for m in messages)


def test_all_criteria_covered_by_every_test_type(tmp_path):
    write(tmp_path, spec_files())
    write(
        tmp_path,
        {
            "tests/test_churn.py": '@pytest.mark.ac("0042/AC-001")\ndef test_x(): ...\n',
            "dbt/models/_fct.unit_tests.yml": "unit_tests:\n  - name: ac_0042_003_runs_fast\n",
        },
    )
    assert messages(check(tmp_path)) == []


@pytest.mark.parametrize(
    "rel, text",
    [
        ("dbt/models/_x.yml", "      - not_null:\n          meta: {ac: 0042/AC-001}\n"),
        ("dbt/tests/assert_x.sql", "{{ config(meta={'ac': '0042/AC-001'}) }}\n"),
        ("evals/datasets/golden.jsonl", '{"input": "Test Person 001 asks", "ac": "0042/AC-001"}\n'),
        ("evals/datasets/golden.csv", "input,ac\nhello,0042/AC-001\n"),
        ("tests/unit/churn_test.py", '@pytest.mark.ac("0042/AC-001", "0042/AC-003")\n'),
    ],
)
def test_other_reference_forms(tmp_path, rel, text):
    write(tmp_path, spec_files())
    write(tmp_path, {rel: text, "tests/test_fast.py": '@pytest.mark.ac("0042/AC-003")\n'})
    assert messages(check(tmp_path)) == []


def test_missing_test_and_unknown_reference_are_both_listed(tmp_path):
    # BUILD-004
    write(tmp_path, spec_files())
    write(tmp_path, {"tests/test_churn.py": '@pytest.mark.ac("0042/AC-001")\n@pytest.mark.ac("0042/AC-009")\n'})
    assert messages(check(tmp_path)) == [
        "tests/test_churn.py:2: 0042/AC-009: spec 0042-churn has no AC-009",
        "specs/0042-churn/spec.md:8: 0042/AC-003 has no test",
    ]


def test_reference_to_unknown_spec(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    write(tmp_path, {"tests/test_x.py": '@pytest.mark.ac("0099/AC-001")\n'})
    assert messages(check(tmp_path)) == ["tests/test_x.py:1: 0099/AC-001: no spec 0099 in specs/"]


def test_unqualified_references_are_rejected(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    write(
        tmp_path,
        {
            "tests/test_x.py": '@pytest.mark.ac("AC-001")\n',
            "dbt/models/_x.unit_tests.yml": "  - name: ac_001_returns_score\n",
            "evals/datasets/g.jsonl": '{"ac": "AC-001"}\n',
        },
    )
    found = messages(check(tmp_path))
    assert len(found) == 3 and all("no spec id" in m for m in found)


def test_superseded_reference_warns(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    write(tmp_path, {"tests/test_x.py": '@pytest.mark.ac("0042/AC-002")\n'})
    findings = check(tmp_path)
    assert messages(findings) == []
    assert "superseded" in messages(findings, "warning")[0]


def test_coverage_only_required_once_tests_are_locked(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    assert messages(check(tmp_path)) == []


def test_open_questions_block_approval(tmp_path):
    write(tmp_path, spec_files(state="approved", questions="- Which Genie spaces use this?\n"))
    assert messages(check(tmp_path, spec_only=True)) == [
        "specs/0042-churn/spec.md:13: open question must be resolved before 'approved': - Which Genie spaces use this?"
    ]
    write(tmp_path, spec_files(state="draft", questions="- Which Genie spaces use this?\n"))
    assert messages(check(tmp_path, spec_only=True)) == []


def test_spec_lint_finds_missing_sections_and_duplicate_ids(tmp_path):
    text = "## 3. Acceptance criteria\n- AC-001 x\n- AC-001 y\n"
    write(tmp_path, {"specs/0042-x/spec.md": text, "specs/0042-x/status.yml": status("draft")})
    found = messages(check(tmp_path, spec_only=True))
    assert "specs/0042-x/spec.md:3: AC-001 is defined twice" in found
    assert sum("missing section" in m for m in found) == 6


def test_pytestmark_counts_but_strings_and_comments_do_not(tmp_path):
    write(tmp_path, spec_files())
    write(
        tmp_path,
        {
            "tests/test_a.py": 'pytestmark = pytest.mark.ac("0042/AC-001")\n',
            "tests/test_b.py": 'X = \'@pytest.mark.ac("0042/AC-003")\'\n# @pytest.mark.ac("0042/AC-003")\n',
        },
    )
    assert messages(check(tmp_path)) == ["specs/0042-churn/spec.md:8: 0042/AC-003 has no test"]


def test_ids_in_code_blocks_are_ignored():
    doc = parse_spec("## 3. Acceptance criteria\n- AC-001 x\n```\n- AC-002 example\n```\n")
    assert list(doc.criteria) == ["AC-001"]


def test_skips_vendored_and_build_folders(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    write(
        tmp_path, {".venv/lib/test_x.py": '@pytest.mark.ac("0099/AC-1")\n', "dbt/target/x.json": '{"ac": "0099/AC-1"}'}
    )
    assert messages(check(tmp_path)) == []


def test_template_folder_is_not_a_spec(tmp_path):
    write(tmp_path, {"specs/_template/spec.md": TEMPLATE, "specs/_template/status.yml": status("draft")})
    assert messages(check(tmp_path)) == []


def test_cli_spec_only(tmp_path, capsys):
    write(tmp_path, spec_files(state="approved", questions="- open?\n"))
    assert main(["--root", str(tmp_path), "--spec-only"]) == 1
    assert "open question" in capsys.readouterr().out


def test_superseded_warning_names_the_replacement(tmp_path):
    write(tmp_path, spec_files(state="approved"))
    write(tmp_path, {"tests/test_x.py": '@pytest.mark.ac("0042/AC-002")\n'})
    assert "point the test at 0042/AC-003" in messages(check(tmp_path), "warning")[0]


def test_pointer_to_an_inactive_criterion_in_the_same_spec_is_an_error():
    doc = parse_spec("## 3. Acceptance criteria\n- AC-001 x\n- ~~AC-002~~ superseded by AC-009\n")
    assert doc.replacements == {"AC-002": (None, "AC-009")}
    assert "AC-002 is superseded by AC-009, which is not an active criterion here" in [m for _, m in doc.problems]


def later_spec(old_line: str) -> dict[str, str]:
    files = spec_files(state="approved")
    old = files["specs/0042-churn/spec.md"].replace("- ~~AC-002~~ superseded by AC-003", old_line)
    return {**files, "specs/0042-churn/spec.md": old, **spec_files(spec_id="0057", state="approved")}


def test_cross_spec_pointer_to_an_active_criterion_passes(tmp_path):
    write(tmp_path, later_spec("- ~~AC-002~~ superseded by 0057/AC-001"))
    assert messages(check(tmp_path, spec_only=True)) == []
    write(tmp_path, {"tests/test_x.py": '@pytest.mark.ac("0042/AC-002")\n'})
    assert "point the test at 0057/AC-001" in messages(check(tmp_path), "warning")[0]


@pytest.mark.parametrize(
    ("line", "error"),
    [
        ("- ~~AC-002~~ superseded by 0099/AC-001", "AC-002 is superseded by 0099/AC-001, but there is no spec 0099"),
        (
            "- ~~AC-002~~ superseded by 0057/AC-002",
            "AC-002 is superseded by 0057/AC-002, which is not an active criterion of spec 0057",
        ),
    ],
)
def test_cross_spec_pointer_must_name_a_real_active_criterion(tmp_path, line, error):
    write(tmp_path, later_spec(line))
    assert any(m.endswith(error) for m in messages(check(tmp_path, spec_only=True)))
