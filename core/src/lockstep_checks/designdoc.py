"""The optional research and design step for large specs: ``research.md`` and ``design.md`` next to ``spec.md``.

A spec needs them when its status.yml says ``design: yes``, or when it has at least ``[specs] design_from_criteria``
active criteria. From ``approved`` on, both must exist with their sections, research.md must name its decision
(``Chosen: <option>, because ...``), and design.md's Open questions must be empty. The step follows SDTRD's
research (Gate 0) and design (Gate 3) gates; in Lockstep both are reviewed in the spec PR.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .specdoc import SpecDoc, list_items, parse_sections
from .status import SpecStatus

RESEARCH = "research.md"
DESIGN = "design.md"
RESEARCH_SECTIONS = {
    1: "Question and constraints",
    2: "Options",
    3: "Trade-offs",
    4: "Criteria this changes",
    5: "Decision",
}
DESIGN_SECTIONS = {
    1: "Overview and invariants",
    2: "Interfaces, data contracts and state",
    3: "Data flow",
    4: "Boundaries and budgets",
    5: "Test seams",
    6: "Open questions",
}
_DECISION = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?chosen\b(?:\*\*)?\s*:?\s*(?P<rest>.*)", re.IGNORECASE)


def needs_design(status: SpecStatus, doc: SpecDoc, cfg: Config) -> bool:
    threshold = cfg.specs.design_from_criteria
    return status.design or (threshold > 0 and len(doc.criteria) >= threshold)


def design_problems(spec_dir: Path, status: SpecStatus, doc: SpecDoc, cfg: Config) -> list[tuple[str, int | None, str]]:
    """(file name, line, message) for each problem; none while the spec is a draft or needs no design step."""
    if status.status == "draft" or not needs_design(status, doc, cfg):
        return []
    why = (
        "design: yes"
        if status.design
        else f"{len(doc.criteria)} criteria, design_from_criteria is {cfg.specs.design_from_criteria}"
    )
    problems: list[tuple[str, int | None, str]] = []
    for name, required in ((RESEARCH, RESEARCH_SECTIONS), (DESIGN, DESIGN_SECTIONS)):
        try:
            text = (spec_dir / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            problems.append((name, None, f"{name} is missing; this spec needs the research and design step ({why})"))
            continue
        sections = parse_sections(text)
        problems += [(name, None, f"missing section '## {n}. {t}'") for n, t in required.items() if n not in sections]
        if name == RESEARCH and 5 in sections and not _decided(sections[5]):
            problems.append((name, None, "section 5 names no decision: add 'Chosen: <option>, because ...'"))
        if name == DESIGN:
            for line, q in list_items(sections.get(6, [])):
                problems.append((name, line, f"open question must be resolved before '{status.status}': {q}"))
    return problems


def _decided(lines: list[tuple[int, str]]) -> bool:
    for _, text in lines:
        m = _DECISION.match(text)
        if m and m["rest"].strip() and not m["rest"].lstrip().startswith("<"):
            return True
    return False
