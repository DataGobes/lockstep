"""Static checks on the Azure Pipelines templates: a typo here would only show up in a real pipeline run."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = sorted((ROOT / "core" / "pipelines").glob("*.yml"))
ROOT_PIPELINES = [ROOT / "templates" / "azure-pipelines-pr.yml", ROOT / "templates" / "azure-pipelines-deploy.yml"]


def declared(text: str) -> set[str]:
    block = re.split(r"\n(?:steps|jobs):", text, maxsplit=1)[0]
    return set(re.findall(r"^  - name: (\w+)$", block, re.MULTILINE))


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_template_uses_only_declared_parameters(path):
    text = path.read_text(encoding="utf-8")
    used = set(re.findall(r"parameters\.(\w+)", text))
    assert used <= declared(text), f"undeclared: {used - declared(text)}"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_template_has_no_tabs_and_starts_with_a_usage_comment(path):
    text = path.read_text(encoding="utf-8")
    assert "\t" not in text
    assert text.startswith("# Lockstep") and "- template: .lockstep/pipelines/" + path.name in text


@pytest.mark.parametrize("root_pipeline", ROOT_PIPELINES, ids=lambda p: p.name)
def test_root_pipeline_references_existing_templates_with_known_parameters(root_pipeline):
    text = root_pipeline.read_text(encoding="utf-8")
    uses = text.split("- template: .lockstep/pipelines/")[1:]
    assert uses
    for use in uses:
        name = use.split(None, 1)[0]
        template = ROOT / "core" / "pipelines" / name
        assert template.is_file(), name
        section = re.split(r"- (?:job|stage):", use, maxsplit=1)[0]
        given = set(re.findall(r"^          (\w+):", section, re.MULTILINE))
        assert given <= declared(template.read_text(encoding="utf-8")), f"{name}: {given}"


GITHUB_PR = ROOT / "templates" / "github-actions-pr.yml"


def test_github_workflow_runs_the_same_checks_as_azure():
    azure = (ROOT / "core" / "pipelines" / "lockstep-pr.yml").read_text(encoding="utf-8")
    checks = re.search(r"default: \[([^\]]+)\]", azure.split("name: checks", 1)[1])[1].split(", ")
    github = GITHUB_PR.read_text(encoding="utf-8")
    assert re.findall(r"python -m lockstep_checks\.check_(\w+)", github) == checks
    for check in re.findall(r"^      - name: \"Lockstep: (\w+)\"\n        if: (.+)$", github, re.MULTILINE):
        assert check[1] == "${{ !cancelled() }}", check[0]


def test_github_workflow_never_pastes_the_pr_title_into_a_script():
    github = GITHUB_PR.read_text(encoding="utf-8")
    assert "\t" not in github
    assert "LOCKSTEP_PR_TITLE: ${{ github.event.pull_request.title }}" in github
    runs = re.findall(r"run: (.+)", github)
    assert runs and not any("${{" in r for r in runs)
