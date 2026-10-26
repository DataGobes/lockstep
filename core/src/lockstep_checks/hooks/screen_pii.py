"""UserPromptSubmit (Claude only): keep personal data out of Claude.

Blocks a prompt that contains an email address, a phone number, a valid IBAN or a
configured PII field name, and every prompt while the active spec has ``pii: yes``.
Either way the user is pointed to the company's Copilot. Copilot also runs this hook
but ignores its result, which is intended: Copilot is where PII work happens.
"""

from __future__ import annotations

import re
import sys

from ..config import load_config
from ..spec import SpecError, current_branch, resolve_spec
from . import Decision, Event, repo_root, run

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
# 9+ digits with optional international prefix and common separators, e.g. +31 6 1234 5678.
_PHONE = re.compile(r"(?<![\w.])(?:\+|00)?\d[\d \-()./]{7,}\d(?![\w.])")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b")

SWITCH = "Personal data must not go to Claude. Continue this task in the company's Copilot."


def _digits(s: str) -> int:
    return sum(c.isdigit() for c in s)


def _valid_iban(candidate: str) -> bool:
    s = candidate.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    moved = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def find_pii(prompt: str, columns: tuple[str, ...]) -> list[str]:
    hits = []
    if _EMAIL.search(prompt):
        hits.append("an email address")
    if any(_digits(m.group()) >= 9 for m in _PHONE.finditer(prompt)):
        hits.append("a phone number")
    if any(_valid_iban(m.group()) for m in _IBAN.finditer(prompt)):
        hits.append("an IBAN")
    for col in columns:
        if re.search(rf"(?<![\w]){re.escape(col)}(?![\w])", prompt, re.IGNORECASE):
            hits.append(f"the PII field name '{col}'")
    return hits


def hook(event: Event) -> Decision:
    root = repo_root(event.cwd)
    cfg = load_config(root)
    try:
        spec = resolve_spec(root, current_branch(root), cfg)
    except SpecError as e:
        return Decision.deny(f"BLOCKED by lockstep: the active spec is broken ({e}), so its PII flag is unknown.")
    if spec.status and spec.status.pii:
        return Decision.deny(f"BLOCKED by lockstep: spec {spec.spec_id} is marked pii: yes. {SWITCH}")
    hits = find_pii(event.prompt, cfg.pii.columns)
    if hits:
        return Decision.deny(
            f"BLOCKED by lockstep: this prompt contains {', '.join(hits)}. {SWITCH} "
            "If it is invented test data, rewrite it with obvious placeholders such as 'Test Person 001'."
        )
    return Decision.allow()


def main() -> None:
    sys.exit(run(hook))
