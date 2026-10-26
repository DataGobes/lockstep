"""Fail a PR that changes existing tests or quietly weakens checks.

Existing files under ``protect.globs`` (tests, dbt unit-test YAML, eval thresholds and
datasets, snapshots) may not be modified, renamed or deleted, and no change may add
skip/xfail markers, disabled or downgraded dbt tests, ``# noqa`` or ``type: ignore``.
New test files are fine. A PR whose title starts with ``[test-change]`` is a deliberate
test change: findings are reported as warnings and the required reviewer decides.
"""

from __future__ import annotations

import re

from .cli import PrContext, main_for
from .config import Config
from .gitdiff import ChangedFile, changed_files
from .paths import matches_any
from .report import Finding

OVERRIDE = "[test-change]"

# (file suffixes, pattern, what it does)
_WEAKENERS: tuple[tuple[tuple[str, ...], re.Pattern[str], str], ...] = tuple(
    (suffixes, re.compile(pattern), label)
    for suffixes, pattern, label in (
        ((".py",), r"@pytest\.mark\.(?:skip|skipif|xfail)\b", "skips or xfails a test"),
        ((".py",), r"\bpytest\.(?:skip|xfail|importorskip)\(", "skips or xfails a test"),
        ((".py",), r"@unittest\.(?:skip\w*|expectedFailure)\b", "skips a test"),
        ((".py",), r"#\s*noqa\b", "silences the linter"),
        ((".py",), r"#\s*(?:type|pyright):\s*ignore\b", "silences the type checker"),
        ((".yml", ".yaml"), r"^\s*(?:-\s*)?enabled:\s*false\b", "disables a dbt test or model"),
        ((".yml", ".yaml"), r"^\s*(?:-\s*)?severity:\s*['\"]?warn\b", "downgrades a dbt test to a warning"),
        ((".sql",), r"\benabled\s*=\s*false\b", "disables a dbt test or model"),
        ((".sql",), r"\bseverity\s*=\s*['\"]warn", "downgrades a dbt test to a warning"),
    )
)


def check_test_tamper(files: list[ChangedFile], cfg: Config, title: str | None) -> list[Finding]:
    protected = cfg.protect.globs
    raw: list[Finding] = []
    for f in files:
        if f.existed_on_base and matches_any(f.base_path, protected):
            action = {"D": "deletes", "R": f"renames (to {f.path})", "C": "copies"}.get(f.status, "modifies")
            if f.status != "C":  # copying a test leaves the original intact
                raw.append(Finding("error", f"{action} an existing test or eval file", path=f.base_path))
        for line_no, text in f.added_lines:
            for suffixes, pattern, label in _WEAKENERS:
                if f.path.endswith(suffixes) and pattern.search(text):
                    raw.append(Finding("error", f"added line {label}: {text.strip()}", path=f.path, line=line_no))
                    break
    if raw and (title or "").startswith(OVERRIDE):
        return [Finding("warning", f"{x.message} (allowed by {OVERRIDE})", x.path, x.line) for x in raw]
    if raw:
        raw.append(
            Finding(
                "error",
                f"If a test is wrong, stop and explain why. A real test change goes in its own PR titled '{OVERRIDE} ...'.",
            )
        )
    return raw


def _run(ctx: PrContext) -> list[Finding]:
    return check_test_tamper(changed_files(ctx.root, ctx.base), ctx.cfg, ctx.title)


if __name__ == "__main__":
    main_for("check_test_tamper", __doc__.splitlines()[0], _run)
