"""Parse a spec's ``spec.md``: its sections and acceptance criteria.

Criteria are list items in section 3 that start with ``AC-<n>``. A superseded
criterion is struck through and points forward, to a criterion in the same spec or a
later one (``- ~~AC-002~~ superseded by AC-007`` or ``superseded by 0057/AC-001``);
it stays in the spec but needs no test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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


@dataclass(frozen=True)
class SpecDoc:
    sections: dict[int, list[tuple[int, str]]]  # section number -> (line number, text) in it
    criteria: dict[str, int]  # active AC id -> line number
    superseded: dict[str, int]
    replacements: dict[str, tuple[str | None, str]]  # superseded AC id -> (spec id or None for this spec, AC id)
    problems: list[tuple[int | None, str]]  # (line number, message)

    def open_questions(self) -> list[tuple[int, str]]:
        return [(n, t.strip()) for n, t in self.sections.get(7, []) if _LIST_ITEM.match(t)]


def parse_spec(text: str) -> SpecDoc:
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

    problems: list[tuple[int | None, str]] = []
    for number, title in REQUIRED_SECTIONS.items():
        if number not in sections:
            problems.append((None, f"missing section '## {number}. {title}'"))

    criteria: dict[str, int] = {}
    superseded: dict[str, int] = {}
    replacements: dict[str, tuple[str | None, str]] = {}
    for n, line in sections.get(3, []):
        m = _AC_ITEM.match(line)
        if not m:
            continue
        ac = m["id"]
        if ac in criteria or ac in superseded:
            problems.append((n, f"{ac} is defined twice"))
            continue
        if not m["struck"]:
            criteria[ac] = n
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
    return SpecDoc(sections, criteria, superseded, replacements, problems)
