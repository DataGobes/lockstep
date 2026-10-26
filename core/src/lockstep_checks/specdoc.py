"""Parse a spec's ``spec.md``: its sections and acceptance criteria.

Criteria are list items in section 3 that start with ``AC-<n>``. A superseded
criterion is struck through and points forward, to a criterion in the same spec or a
later one (``- ~~AC-002~~ superseded by AC-007`` or ``superseded by 0057/AC-001``);
it stays in the spec but needs no test.

A criterion is one EARS sentence (``- AC-001 WHEN <trigger> THE <system> SHALL <behaviour>.``) or a title with
Given/When/Then steps indented under it (``  - GIVEN ...``, ``  - WHEN ...``, ``  - THEN ...``, plus ``AND``/``BUT``).
``[specs] ac_format`` in lockstep.toml can require one of the two; steps are checked for order either way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise

REQUIRED_SECTIONS = {
    1: "Problem and outcome",
    2: "Scope / non-goals",
    3: "Acceptance criteria",
    4: "Interfaces and data contract",
    5: "Test and eval plan",
    6: "Risks, rollout, rollback",
    7: "Open questions",
}

_HEADING = re.compile(r"^##\s+(\d+)\.\s*(.*?)\s*$")
_AC_ITEM = re.compile(r"^\s*[-*]\s+(?P<struck>~~)?(?P<id>AC-\d+)\b")
_POINTER = re.compile(r"\bsuperseded\s+by\s+(?:(?P<spec>\d+)/)?(?P<ac>AC-\d+)\b", re.IGNORECASE)
_LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S")
_STEP = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?P<kw>given|when|then|and|but)\b", re.IGNORECASE)
_SHALL = re.compile(r"\bSHALL\b")


@dataclass(frozen=True)
class SpecDoc:
    sections: dict[int, list[tuple[int, str]]]  # section number -> (line number, text) in it
    criteria: dict[str, int]  # active AC id -> line number
    superseded: dict[str, int]
    replacements: dict[str, tuple[str | None, str]]  # superseded AC id -> (spec id or None for this spec, AC id)
    problems: list[tuple[int | None, str]]  # (line number, message)
    text: dict[str, list[str]] = field(default_factory=dict)  # active AC id -> its lines, steps included

    def open_questions(self) -> list[tuple[int, str]]:
        return list_items(self.sections.get(7, []))


def parse_sections(text: str) -> dict[int, list[tuple[int, str]]]:
    """Numbered ``## <n>. Title`` sections -> their (line number, text) lines, code blocks left out."""
    sections: dict[int, list[tuple[int, str]]] = {}
    current: int | None = None
    in_code = False
    for n, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        m = _HEADING.match(line)
        if m:
            current = int(m[1])
            sections.setdefault(current, [])
        elif line.startswith("## "):
            current = None
        elif current is not None:
            sections[current].append((n, line))
    return sections


def list_items(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(n, t.strip()) for n, t in lines if _LIST_ITEM.match(t)]


def parse_spec(text: str, ac_format: str = "any") -> SpecDoc:
    sections = parse_sections(text)
    problems: list[tuple[int | None, str]] = []
    for number, title in REQUIRED_SECTIONS.items():
        if number not in sections:
            problems.append((None, f"missing section '## {number}. {title}'"))

    criteria: dict[str, int] = {}
    superseded: dict[str, int] = {}
    replacements: dict[str, tuple[str | None, str]] = {}
    blocks: dict[str, list[str]] = {}
    section3 = sections.get(3, [])
    for i, (n, line) in enumerate(section3):
        m = _AC_ITEM.match(line)
        if not m:
            continue
        ac = m["id"]
        if ac in criteria or ac in superseded:
            problems.append((n, f"{ac} is defined twice"))
            continue
        if not m["struck"]:
            criteria[ac] = n
            blocks[ac] = [line.strip(), *_continuation(section3[i + 1 :], _indent(line))]
            problems.extend((n, f"{ac} {msg}") for msg in _format_problems(blocks[ac], ac_format))
            continue
        superseded[ac] = n
        pointer = _POINTER.search(line, m.end())
        if pointer:
            replacements[ac] = (pointer["spec"], pointer["ac"])
    if 3 in sections and not criteria:
        problems.append((None, "section 3 has no acceptance criteria (list items starting with AC-001)"))
    for ac, (spec, target) in replacements.items():
        if spec is None and target not in criteria:
            problems.append((superseded[ac], f"{ac} is superseded by {target}, which is not an active criterion here"))
    return SpecDoc(sections, criteria, superseded, replacements, problems, blocks)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _continuation(rest: list[tuple[int, str]], indent: int) -> list[str]:
    """The lines indented under a list item, up to the next line that is not."""
    lines = []
    for _, line in rest:
        if line.strip() and _indent(line) <= indent:
            break
        if line.strip():
            lines.append(line.strip())
    return lines


def _format_problems(block: list[str], ac_format: str) -> list[str]:
    steps = [m["kw"].upper() for line in block[1:] if (m := _STEP.match(line))]
    if ac_format == "ears":
        if steps:
            return ["has Given/When/Then steps; this repo writes criteria in EARS (ac_format = 'ears')"]
        return [] if _SHALL.search(" ".join(block)) else ["is not EARS: it needs '... THE <system> SHALL <behaviour>'"]
    if not steps:
        if ac_format == "given-when-then":
            return ["needs Given/When/Then steps under it (ac_format = 'given-when-then')"]
        return []
    return _step_order(steps)


def _step_order(steps: list[str]) -> list[str]:
    """GIVEN steps (optional), then WHEN, then THEN; AND and BUT continue the step before them."""
    if steps[0] in ("AND", "BUT"):
        return [f"starts with {steps[0]}; start with GIVEN or WHEN"]
    kinds = []
    for step in steps:
        kinds.append(kinds[-1] if step in ("AND", "BUT") else step)
    order = {"GIVEN": 0, "WHEN": 1, "THEN": 2}
    if any(order[a] > order[b] for a, b in pairwise(kinds)):
        return ["has its steps out of order: GIVEN, then WHEN, then THEN"]
    missing = [k for k in ("WHEN", "THEN") if k not in kinds]
    return [f"has no {' or '.join(missing)} step"] if missing else []
