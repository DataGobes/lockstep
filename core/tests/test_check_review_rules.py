from pathlib import Path

import pytest

from lockstep_checks.check_review_rules import END, GENERATED, START, check_review_rules, find_block, render

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "AGENTS.md"
AGENTS = (
    f"# Agents\n\nIntro.\n\n{START}\n## Lockstep review rules\n\n- Flag a test that cannot fail.\n{END}\n\n## More\n"
)
RULES = "## Lockstep review rules\n\n- Flag a test that cannot fail."


def setup(root: Path, agents: str | None = AGENTS, instructions: str | None = None, folder: str = ".github") -> Path:
    if agents is not None:
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    target = root / folder / "copilot-instructions.md"
    if instructions is not None:
        target.parent.mkdir(parents=True)
        target.write_text(instructions, encoding="utf-8")
    return target


def levels(findings):
    return [f.level for f in findings]


def test_write_creates_the_file_then_check_passes(tmp_path):
    target = setup(tmp_path)
    assert levels(check_review_rules(tmp_path)) == ["error"]
    assert levels(check_review_rules(tmp_path, write=True)) == ["warning"]
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Review rules for this repository\n")
    assert f"{GENERATED}\n{RULES}\n{END}\n" in text
    assert check_review_rules(tmp_path) == []


def test_write_keeps_the_repo_rules_and_puts_the_block_under_the_title(tmp_path):
    own = "# Repo rules\n\nProject rules also apply.\n\n## Domain rules\n- Amounts are in cents.\n"
    target = setup(tmp_path, instructions=own)
    check_review_rules(tmp_path, write=True)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == ["# Repo rules", "", GENERATED]
    assert lines[-2:] == ["## Domain rules", "- Amounts are in cents."]


def test_write_replaces_only_the_block(tmp_path):
    old = f"# Repo rules\n\n{GENERATED}\n## Old\n- stale rule\n{END}\n\n## Domain rules\n- Amounts are in cents.\n"
    target = setup(tmp_path, instructions=old)
    finding = check_review_rules(tmp_path)[0]
    assert finding.level == "error" and "differ from AGENTS.md" in finding.message
    check_review_rules(tmp_path, write=True)
    text = target.read_text(encoding="utf-8")
    assert "stale rule" not in text
    assert text == old.replace("## Old\n- stale rule", RULES)


def test_write_is_stable(tmp_path):
    target = setup(tmp_path, instructions="# Repo rules\n")
    check_review_rules(tmp_path, write=True)
    once = target.read_text(encoding="utf-8")
    assert render(once, RULES) == once


def test_azuredevops_folder_is_used_when_the_repo_has_it(tmp_path):
    target = setup(tmp_path, instructions="# Repo rules\n", folder=".azuredevops")
    check_review_rules(tmp_path, write=True)
    assert START.removesuffix(" -->") in target.read_text(encoding="utf-8")
    assert not (tmp_path / ".github").exists()


def test_no_agents_block_is_only_a_warning(tmp_path):
    assert levels(check_review_rules(tmp_path)) == ["warning"]
    setup(tmp_path, agents="# Agents\n")
    assert levels(check_review_rules(tmp_path)) == ["warning"]


@pytest.mark.parametrize(
    "text",
    [f"{START}\n- a\n", f"- a\n{END}\n", f"{START}\n- a\n{END}\n{START}\n- b\n{END}\n", f"{END}\n- a\n{START}\n"],
)
def test_broken_markers_are_errors(tmp_path, text):
    setup(tmp_path, agents=text)
    finding = check_review_rules(tmp_path)[0]
    assert finding.level == "error" and finding.path == "AGENTS.md"


def test_template_has_a_review_rules_block():
    block = find_block(TEMPLATE.read_text(encoding="utf-8"), "AGENTS.md")
    assert block is not None
    rules = [line for line in block.body.splitlines() if line.startswith("- ")]
    assert 5 <= len(rules) <= 10  # leaves room in Copilot's 10-20 rule budget for the repo's own rules
