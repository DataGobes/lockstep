"""The SDTRD spec format: an SDTRD repo as it is, read through the SDTRD profile in templates/sdtrd/lockstep.toml."""

import shutil
from pathlib import Path

import pytest

from lockstep_checks import sdtrd
from lockstep_checks.check_ac_traceability import check_traceability
from lockstep_checks.check_spec_required import check_spec_required
from lockstep_checks.config import ConfigError, load_config
from lockstep_checks.gitdiff import ChangedFile
from lockstep_checks.lock import lock_commit
from lockstep_checks.spec import list_specs, resolve_spec

PROFILE = Path(__file__).resolve().parents[2] / "templates" / "sdtrd" / "lockstep.toml"
FEATURE = "specs/features/w1.2-token-check"


def spec_md(gate2: bool, reqs: str = "") -> str:
    reqs = reqs or (
        "- **REQ-AUTH-1 (Token check)**: The system MUST reject an empty token.\n"
        "- **NFR-AUTH-1 (Latency)**: Token checks MUST complete within `5 ms`.\n"
    )
    return (
        "# Specification: Token check\n\n## Capability: `tokens`\n\n### 1. Functional Requirements\n\n"
        f"{reqs}\n- **ASM-AUTH-1**: Tokens are ASCII.\n\n## Review Gate\n"
        f"- [{'x' if gate2 else ' '}] **Gate 2 Approval**: Specifications reviewed and approved by human.\n"
    )


def tasks_md(gate4: bool, gate6: bool = False) -> str:
    return (
        "# Task Breakdown: Token check\n\n### Slice 1: Core\n"
        "- [x] 1.2 **Review Gate 5.1**: Human sign-off on BDD scenarios.\n\n## 4. Integration\n"
        f"- [{'x' if gate4 else ' '}] **Gate 4 Approval**: Tasks breakdown approved by human.\n"
        f"- [{'x' if gate6 else ' '}] **Gate 6 Approval**: Final sync and archive sign-off.\n"
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    shutil.copy(PROFILE, tmp_path / "lockstep.toml")
    return tmp_path


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def feature(root: Path, gate2=True, gate4=True, gate6=False, folder=FEATURE, reqs="") -> None:
    write(root, f"{folder}/specs/tokens/spec.md", spec_md(gate2, reqs))
    write(root, f"{folder}/tasks.md", tasks_md(gate4, gate6))


def messages(findings, level="error"):
    return [f.message for f in findings if f.level == level]


# Config


def test_profile_loads(repo):
    cfg = load_config(repo)
    assert (cfg.specs.format, cfg.lanes.feature, cfg.lanes.bugfix, cfg.jira_required) == (
        "sdtrd",
        ("feat/",),
        ("fix/",),
        False,
    )


@pytest.mark.parametrize(
    "text, error",
    [
        ('[specs]\nformat = "openspec"\n', "specs.format must be one of lockstep, sdtrd"),
        ('[specs]\nformat = "sdtrd"\nliving = true\n', "SDTRD keeps its own"),
        ('[lanes]\nfeature = ["chore/"]\n', "distinct branch prefixes"),
        ("[lanes]\nfeature = []\n", "distinct branch prefixes"),
    ],
)
def test_bad_format_settings_fail(tmp_path, text, error):
    write(tmp_path, "lockstep.toml", text)
    with pytest.raises(ConfigError, match=error):
        load_config(tmp_path)


# Gates and status


def test_gates_reads_ticked_and_open_boxes():
    text = "- [x] **Gate 2 Approval**: ok\n- [ ] **Gate 4 Approval**\n- [X] 1.2 **Review Gate 5.1**: BDD\n"
    text += "- [x] **Gate B1 (Triage & Root Cause)**: ok\n  - [ ] not a gate\n"
    assert sdtrd.gates(text) == {"2": True, "4": False, "5.1": True, "B1": True}


def test_a_gate_listed_twice_needs_every_box():
    assert sdtrd.gates("- [x] **Gate 2 Approval**\n- [ ] **Gate 2 Approval**\n") == {"2": False}


@pytest.mark.parametrize(
    "gate2, gate4, gate6, status",
    [
        (False, False, False, "draft"),
        (True, False, False, "approved"),
        (True, True, False, "tests-locked"),
        (True, True, True, "implemented"),
    ],
)
def test_status_comes_from_the_gate_boxes(repo, gate2, gate4, gate6, status):
    feature(repo, gate2, gate4, gate6)
    res = resolve_spec(repo, "feat/w1.2-token-check", load_config(repo))
    assert (res.state, res.spec_id, res.status.status) == ("found", "w1.2", status)


def test_a_feature_with_one_unapproved_capability_is_still_draft(repo):
    feature(repo)
    write(repo, f"{FEATURE}/specs/sessions/spec.md", spec_md(False, "- **REQ-SESS-1 (x)**: The system MUST x.\n"))
    write(repo, f"{FEATURE}/tasks.md", tasks_md(False))
    assert resolve_spec(repo, "feat/w1.2-token-check", load_config(repo)).status.status == "draft"


def test_research_only_is_draft(repo):
    write(repo, f"{FEATURE}/research.md", "# Research\n")
    assert resolve_spec(repo, "feat/w1.2-token-check", load_config(repo)).status.status == "draft"


def test_status_points_at_the_file_whose_gate_sets_it(repo):
    feature(repo, gate4=False)
    res = resolve_spec(repo, "feat/w1.2-token-check", load_config(repo))
    assert res.status_path == Path(f"{FEATURE}/specs/tokens/spec.md")
    feature(repo)
    res = resolve_spec(repo, "feat/w1.2-token-check", load_config(repo))
    assert res.status_path == Path(f"{FEATURE}/tasks.md")


def test_stream_branches_and_archived_features_resolve(repo):
    feature(repo, folder="specs/archive/w1.1-login")
    cfg = load_config(repo)
    res = resolve_spec(repo, "feat/w1.1/stream-a", cfg)
    assert (res.state, res.spec_id, res.status.status) == ("found", "w1.1", "implemented")
    assert resolve_spec(repo, "fix/login-crash", cfg).state == "no-match"
    assert resolve_spec(repo, "feat/w9.9-new", cfg).state == "missing"


def test_list_specs_finds_features_and_archive_and_rejects_duplicates(repo):
    feature(repo)
    feature(repo, folder="specs/archive/w1.1-login")
    write(repo, "specs/features/.gitkeep", "")
    assert sorted(list_specs(repo, load_config(repo))) == ["w1.1", "w1.2"]
    feature(repo, folder="specs/archive/w1.2-token-check-old")
    with pytest.raises(ValueError, match="w1.2 has more than one folder"):
        list_specs(repo, load_config(repo))


def test_sdtrd_has_no_lock_commit(repo):
    feature(repo)
    cfg = load_config(repo)
    res = resolve_spec(repo, "feat/w1.2-token-check", cfg)
    assert lock_commit(repo, "origin/main", res, cfg) is None


# Requirements


def test_parse_requirements_keys_deprecations_and_problems():
    text = (
        "- **REQ-AUTH-1 (Check)**: MUST check.\n"
        "- REQ-AUTH-2: MUST log. [DEPRECATED by w1.3]\n"
        "- **NFR-DATA-INGEST-1 (Latency)**: within `5 ms`.\n"
        "```\n- REQ-AUTH-9: inside a code block\n```\n"
        "- **REQ-AUTH-1 (Again)**: MUST again.\n"
        "- **Edge Case 1**: mentions REQ-AUTH-1 but defines nothing.\n"
    )
    reqs = sdtrd.parse_requirements(Path("spec.md"), text)
    assert reqs.active == {"REQ-AUTH-1": 1, "NFR-DATA-INGEST-1": 3}
    assert reqs.deprecated == {"REQ-AUTH-2": 2}
    assert reqs.problems == [(7, "REQ-AUTH-1 is defined twice")]


def test_a_spec_without_requirements_is_a_problem():
    assert sdtrd.parse_requirements(Path("spec.md"), "# Spec\n").problems[0][1].startswith("defines no requirements")


# Traceability


def test_a_locked_feature_needs_a_test_per_requirement(repo):
    feature(repo)
    write(repo, "tests/bdd/features/tokens.feature", "@REQ-AUTH-1\nScenario: empty token\n")
    found = check_traceability(repo, load_config(repo), spec_only=False)
    assert messages(found) == ["requirement NFR-AUTH-1 has no test (name it in a test, e.g. @NFR-AUTH-1)"]
    assert found[0].path == f"{FEATURE}/specs/tokens/spec.md"
    write(repo, "tests/test_tokens.py", "def test_latency():  # NFR-AUTH-1\n    pass\n")
    assert check_traceability(repo, load_config(repo), spec_only=False) == []


def test_a_feature_before_gate_4_needs_no_tests_yet(repo):
    feature(repo, gate4=False)
    assert check_traceability(repo, load_config(repo), spec_only=False) == []


def test_tests_must_name_keys_that_exist(repo):
    feature(repo, gate4=False)
    write(repo, "tests/test_x.py", "def test_x():  # REQ-AUTH-7\n    pass\n")
    write(repo, "src/app.py", "# REQ-NOPE-1 in product code is not a test reference\n")
    found = check_traceability(repo, load_config(repo), spec_only=False)
    assert messages(found) == ["REQ-AUTH-7: no spec in specs/ defines it"]
    assert (found[0].path, found[0].line) == ("tests/test_x.py", 1)


def test_living_specs_without_tests_are_warnings(repo):
    write(repo, "specs/living/tokens/spec.md", spec_md(True))
    write(repo, "tests/test_tokens.py", "# REQ-AUTH-1\n")
    found = check_traceability(repo, load_config(repo), spec_only=False)
    assert messages(found) == []
    assert messages(found, "warning") == [
        "shipped requirement NFR-AUTH-1 has no test (name it in a test, e.g. @NFR-AUTH-1)"
    ]


def test_shipped_features_count_through_living_specs_not_the_archive(repo):
    feature(repo, folder="specs/archive/w1.1-login")
    assert check_traceability(repo, load_config(repo), spec_only=False) == []


def test_a_test_on_a_deprecated_requirement_is_a_warning(repo):
    feature(
        repo, gate4=False, reqs="- **REQ-AUTH-1 (x)**: MUST x. [DEPRECATED by w1.3]\n- **REQ-AUTH-2 (y)**: MUST y.\n"
    )
    write(repo, "tests/test_x.py", "# REQ-AUTH-1\n")
    found = check_traceability(repo, load_config(repo), spec_only=False)
    assert messages(found, "warning") == ["REQ-AUTH-1 is deprecated; point the test at what replaced it"]


def test_an_approved_feature_needs_a_capability_spec(repo):
    write(repo, f"{FEATURE}/tasks.md", tasks_md(True))
    found = check_traceability(repo, load_config(repo), spec_only=True)
    assert messages(found) == ["is tests-locked but has no capability spec (specs/<capability>/spec.md)"]


# Lanes


CODE = ChangedFile("src/app.rs", "M")


def lane(repo, branch, files, into_main=None):
    cfg = load_config(repo)
    return check_spec_required(files, branch, resolve_spec(repo, branch, cfg), cfg, into_main, repo)


def test_feat_code_needs_gate_4(repo):
    feature(repo, gate4=False)
    found = messages(lane(repo, "feat/w1.2-token-check", [CODE]))
    assert found == [
        (
            "spec w1.2 is approved; a feature PR that changes code needs it tests-locked or implemented "
            "(tick Gate 4 in tasks.md)"
        )
    ]


def test_feat_into_main_needs_gate_6(repo):
    feature(repo)
    assert lane(repo, "feat/w1.2-token-check", [CODE]) == []
    found = lane(repo, "feat/w1.2-token-check", [CODE], into_main="error")
    assert messages(found) == [
        (
            "spec w1.2 is still tests-locked; as the last commit before the PR into main, tick Gate 6 in tasks.md, "
            "so once this merges the spec shows as done"
        )
    ]
    assert found[0].path == f"{FEATURE}/tasks.md"
    feature(repo, gate6=True)
    assert lane(repo, "feat/w1.2-token-check", [CODE], into_main="error") == []


def test_a_stream_pr_into_its_feature_branch_is_not_into_main(repo):
    from lockstep_checks.check_spec_required import _into_main

    assert _into_main("origin/feat/w1.2-token-check", load_config(repo)) is None


def test_chore_and_spec_only_changes_need_nothing(repo):
    assert lane(repo, "chore/bump-deps", [CODE]) == []
    assert lane(repo, "feat/w1.2-token-check", [ChangedFile(f"{FEATURE}/research.md", "A")]) == []
    assert lane(repo, "chore/ci", [ChangedFile(".github/workflows/lockstep.yml", "A")]) == []


def test_code_on_another_branch_names_the_sdtrd_lanes(repo):
    assert messages(lane(repo, "my-work", [CODE]))[0].endswith(
        "Use feat/<id>- for a tests-locked spec, or one of fix/, chore/ for a bug or a chore"
    )


def test_missing_feature_folder_names_specs_features(repo):
    assert messages(lane(repo, "feat/w9.9-new", [CODE])) == [
        "branch names spec w9.9 but specs/features/w9.9-*/ does not exist"
    ]


REPORT = "specs/bug-reports/2026-10-27-empty-token.md"


def bug_report(b1: bool) -> str:
    return f"# Bug Report: empty token\n\n## Review Gates\n- [{'x' if b1 else ' '}] **Gate B1 (Triage & Root Cause)**: ok\n"


def test_fix_needs_a_triaged_bug_report_and_a_regression_test(repo):
    files = [CODE, ChangedFile(REPORT, "A"), ChangedFile("tests/test_empty_token.py", "A")]
    write(repo, REPORT, bug_report(False))
    found = lane(repo, "fix/empty-token", files)
    assert messages(found) == ["the bug report's Gate B1 (triage and root cause) is not ticked; code waits for it"]
    assert found[0].path == REPORT
    write(repo, REPORT, bug_report(True))
    assert lane(repo, "fix/empty-token", files) == []


def test_fix_without_a_report_names_the_sdtrd_file_name(repo):
    found = messages(lane(repo, "fix/empty-token", [CODE, ChangedFile("tests/test_x.py", "A")]))
    assert found == ["a bugfix PR needs its bug report: add specs/bug-reports/<date>-<slug>.md from the template"]
