"""Static checks on the Azure Pipelines templates: a typo here would only show up in a real pipeline run."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = sorted((ROOT / "core" / "pipelines").glob("*.yml"))
ROOT_PIPELINE = ROOT / "templates" / "azure-pipelines-pr.yml"


def declared(text: str) -> set[str]:
    block = text.split("\nsteps:", 1)[0]
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


def test_root_pipeline_references_existing_templates_with_known_parameters():
    text = ROOT_PIPELINE.read_text(encoding="utf-8")
    refs = re.findall(r"- template: \.lockstep/pipelines/(\S+)", text)
    assert refs
    for name in refs:
        template = ROOT / "core" / "pipelines" / name
        assert template.is_file(), name
        section = text.split(f"pipelines/{name}", 1)[1].split("- job:", 1)[0]
        given = set(re.findall(r"^          (\w+):", section, re.MULTILINE))
        assert given <= declared(template.read_text(encoding="utf-8")), f"{name}: {given}"
