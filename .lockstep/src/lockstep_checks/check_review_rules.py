"""Keep the Lockstep review rules in copilot-instructions.md in sync with AGENTS.md.

AGENTS.md is the one source of the workflow rules. Copilot code review on Azure DevOps
does not read AGENTS.md and does not follow links, so the review rules are copied into
``.github/copilot-instructions.md`` (or ``.azuredevops/`` if the repo uses that) between
markers. This check fails when the copy is missing or differs; ``--write`` updates it and
leaves everything outside the markers alone, so the repo's own rules are kept.

In AGENTS.md:
  <!-- lockstep:review-rules -->
  ## Review rules
  - ...
  <!-- /lockstep:review-rules -->
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli import run
from .report import Finding

AGENTS = "AGENTS.md"
START = "<!-- lockstep:review-rules -->"
END = "<!-- /lockstep:review-rules -->"
GENERATED = (
    "<!-- lockstep:review-rules: copied from AGENTS.md by `python -m lockstep_checks.check_review_rules --write`."
    " Edit AGENTS.md, not this block. -->"
)
_START_ANY = re.compile(r"^<!-- lockstep:review-rules\b.*-->$")
_TITLE = "# Review rules for this repository\n"


class BlockError(ValueError):
    pass


@dataclass(frozen=True)
class Block:
    start: int  # index of the start-marker line
    end: int  # index of the end-marker line
    body: str  # the lines between the markers, stripped of blank edges


def find_block(text: str, name: str) -> Block | None:
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if _START_ANY.match(line.strip())]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise BlockError(f"{name}: needs exactly one {START} ... {END} block")
    return Block(starts[0], ends[0], "\n".join(lines[starts[0] + 1 : ends[0]]).strip("\n"))


def instructions_path(root: Path) -> Path:
    # Same choice as the copilot-review-instructions skill: .azuredevops/ only if the repo already uses it.
    ado = root / ".azuredevops" / "copilot-instructions.md"
    return ado if ado.is_file() else root / ".github" / "copilot-instructions.md"


def render(text: str | None, rules: str) -> str:
    block = f"{GENERATED}\n{rules}\n{END}"
    if text is None:
        return f"{_TITLE}\n{block}\n"
    found = find_block(text, "copilot-instructions.md")
    lines = text.splitlines()
    if found:
        lines[found.start : found.end + 1] = block.splitlines()
    else:
        # Near the top: older guidance says only the first ~4,000 characters are read.
        at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
        lines[at:at] = ["", *block.splitlines(), ""] if at else [*block.splitlines(), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def check_review_rules(root: Path, write: bool = False) -> list[Finding]:
    agents = root / AGENTS
    try:
        source = find_block(agents.read_text(encoding="utf-8"), AGENTS) if agents.is_file() else None
    except BlockError as e:
        return [Finding("error", str(e), AGENTS)]
    if source is None:
        return [Finding("warning", f"{AGENTS} has no {START} block; nothing to copy for Copilot review")]

    target = instructions_path(root)
    rel = target.relative_to(root).as_posix()
    text = target.read_text(encoding="utf-8") if target.is_file() else None
    try:
        current = find_block(text, rel) if text is not None else None
    except BlockError as e:
        return [Finding("error", str(e), rel)]
    if current is not None and current.body == source.body:
        return []
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(text, source.body), encoding="utf-8")
        return [Finding("warning", f"updated the review rules from {AGENTS}; commit the change", rel)]
    what = "are missing" if current is None else f"differ from {AGENTS}"
    hint = "run python -m lockstep_checks.check_review_rules --write and commit"
    return [Finding("error", f"the Lockstep review rules {what}; {hint}", rel)]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in argv
    if write:
        argv.remove("--write")
    return run(
        "check_review_rules",
        __doc__.splitlines()[0] + " Add --write to update the copy.",
        lambda ctx: check_review_rules(ctx.root, write),
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
