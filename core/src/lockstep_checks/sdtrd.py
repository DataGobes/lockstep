"""Read an SDTRD repo as it is: its spec layout, requirement keys and gate checkboxes (``[specs] format = "sdtrd"``).

SDTRD (github.com/mgabs/SDTRD) keeps a feature in ``specs/features/<id>-<slug>/`` with one spec per capability in
``specs/<capability>/spec.md``, and moves the folder to ``specs/archive/`` when it ships, after copying its specs to
``specs/living/<capability>/spec.md``. Ids come from the roadmap, lowercased (``w1.2``). Requirements are keyed
``REQ-<DOMAIN>-<N>`` and ``NFR-<DOMAIN>-<N>``, unique across the repo, and are never reused: a retired one stays,
marked ``[DEPRECATED by <id>]``.

There is no status file. A gate passes when its Review Gate box is ticked and committed, so the status is read from
the boxes:

  implemented   the folder is in specs/archive/, or Gate 6 is ticked in tasks.md
  tests-locked  Gate 4 is ticked in tasks.md (tasks approved; tests and code follow, slice by slice)
  approved      Gate 2 is ticked in every capability spec
  draft         otherwise

A test covers a requirement by naming its key anywhere in a file under ``[protect] globs``: a Gherkin tag
(``@REQ-AUTH-1``), a test name, a comment. Keys are unique, so no spec id is needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .status import SpecStatus

FEATURES = "features"
ARCHIVE = "archive"
LIVING = "living"

KEY = r"(?:REQ|NFR)-[A-Z][A-Z0-9_]*(?:-[A-Z][A-Z0-9_]*)*-\d+"
_KEY = re.compile(rf"(?<![\w-]){KEY}(?![\w-])")
# "- **REQ-AUTH-1 (Token check)**: The system MUST ..." or "- REQ-AUTH-1: ..."
_DEFINITION = re.compile(rf"^\s*[-*]\s+(?:\*\*)?(?P<key>{KEY})\b")
_DEPRECATED = re.compile(r"\[DEPRECATED\s+by\s+(?P<by>[^\]]+)\]", re.IGNORECASE)
_GATE = re.compile(r"^\s*[-*]\s+\[(?P<tick>[ xX])\]\s+(?:[\d.]+\s+)?\*{0,2}(?:Review\s+)?Gate\s+(?P<gate>B?[\d.]+)\b")
_FOLDER = re.compile(r"^(?P<id>[a-z0-9][a-z0-9.]*)-[a-z0-9]")


@dataclass(frozen=True)
class Requirements:
    """The requirement keys one spec file defines."""

    path: Path
    active: dict[str, int]  # key -> line
    deprecated: dict[str, int]
    problems: list[tuple[int, str]]


def spec_folders(root: Path, cfg: Config) -> dict[str, Path]:
    """Every feature folder by id, active ones in specs/features/ and shipped ones in specs/archive/."""
    found: dict[str, Path] = {}
    for area in (FEATURES, ARCHIVE):
        base = Path(root) / cfg.specs_dir / area
        for p in sorted(base.iterdir()) if base.is_dir() else []:
            m = _FOLDER.match(p.name)
            if not (p.is_dir() and m):
                continue
            if m["id"] in found:
                raise ValueError(
                    f"feature id {m['id']} has more than one folder: {_rel(root, found[m['id']])}, {_rel(root, p)}"
                )
            found[m["id"]] = p
    return found


def find_folder(root: Path, spec_id: str, cfg: Config) -> list[Path]:
    return [
        p
        for area in (FEATURES, ARCHIVE)
        for p in sorted((Path(root) / cfg.specs_dir / area).glob(f"{spec_id}-*"))
        if p.is_dir()
    ]


def gates(text: str) -> dict[str, bool]:
    """Gate name ("2", "5.1", "B1") -> ticked. A gate listed twice counts as ticked only if every box is."""
    found: dict[str, bool] = {}
    for line in text.splitlines():
        if m := _GATE.match(line):
            found[m["gate"]] = found.get(m["gate"], True) and m["tick"] != " "
    return found


def ticked(path: Path, gate: str) -> bool:
    try:
        return gates(path.read_text(encoding="utf-8")).get(gate, False)
    except OSError:
        return False


def spec_files(folder: Path) -> list[Path]:
    """The capability specs of a feature folder (``specs/<capability>/spec.md``), or of specs/living/."""
    return sorted(folder.glob("specs/*/spec.md")) if folder.name != LIVING else sorted(folder.glob("*/spec.md"))


def load_status(root: Path, folder: Path, cfg: Config) -> SpecStatus:
    tasks = folder / "tasks.md"
    if folder.parent.name == ARCHIVE or ticked(tasks, "6"):
        status = "implemented"
    elif ticked(tasks, "4"):
        status = "tests-locked"
    elif (specs := spec_files(folder)) and all(ticked(p, "2") for p in specs):
        status = "approved"
    else:
        status = "draft"
    return SpecStatus(status=status, pii=False, track=cfg.tracks[0], jira=None, locked_at_commit=None)


def status_source(folder: Path, status: str) -> Path:
    """The file whose gate box sets ``status``: where a finding about it should point."""
    if status in ("tests-locked", "implemented"):
        return folder / "tasks.md"
    specs = spec_files(folder)
    return specs[0] if specs else folder


def how_to_reach(status: str) -> str:
    return {
        "approved": "tick Gate 2 in each specs/<capability>/spec.md",
        "tests-locked": "tick Gate 4 in tasks.md",
        "implemented": "tick Gate 6 in tasks.md",
    }[status]


def parse_requirements(path: Path, text: str) -> Requirements:
    active: dict[str, int] = {}
    deprecated: dict[str, int] = {}
    problems: list[tuple[int, str]] = []
    in_code = False
    for n, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _DEFINITION.match(line)
        if not m:
            continue
        key = m["key"]
        if key in active or key in deprecated:
            problems.append((n, f"{key} is defined twice"))
        elif _DEPRECATED.search(line):
            deprecated[key] = n
        else:
            active[key] = n
    if not active and not deprecated:
        problems.append((1, "defines no requirements (list items starting with REQ-<DOMAIN>-<N> or NFR-<DOMAIN>-<N>)"))
    return Requirements(path, active, deprecated, problems)


def key_refs(text: str) -> list[tuple[str, int]]:
    """(key, line) for every requirement key named in a test file's text."""
    return [(m[0], n) for n, line in enumerate(text.splitlines(), start=1) for m in _KEY.finditer(line)]


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
