"""Fail a PR that changes existing tests or quietly weakens checks.

Existing files under ``protect.globs`` (tests, dbt unit-test YAML, eval thresholds and
datasets, snapshots) may not be modified, renamed or deleted, and no change may add
skip/xfail markers, disabled or downgraded dbt tests, ``# noqa`` or ``type: ignore``.
New test files are fine. A PR whose title starts with ``[test-change]`` is a deliberate
test change: findings are reported as warnings and the required reviewer decides.

On a feature branch the spec's own tests are new to main but locked since the test PR merged
into the branch (lock.py), so changes to them since that commit fail too.
"""

from __future__ import annotations

import re

from .cli import PrContext, main_for
from .config import Config
from .gitdiff import ChangedFile, changed_files
from .lock import branch_tip, lock_commit
from .paths import matches_any
from .report import Finding
from .spec import resolve_spec

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


def check_test_tamper(
    files: list[ChangedFile], cfg: Config, title: str | None, since_lock: list[ChangedFile] = ()
) -> list[Finding]:
    """``files`` is the PR's diff; ``since_lock`` the diff since the spec's lock commit, on a feature branch."""
    protected = cfg.protect.globs
    raw: list[Finding] = []
    touched = [(f, "an existing test or eval file") for f in files] + [(f, "a locked test") for f in since_lock]
    seen = set()
    for f, what in touched:
        # copying a test leaves the original intact
        if f.existed_on_base and f.status != "C" and matches_any(f.base_path, protected) and f.base_path not in seen:
            seen.add(f.base_path)
            action = {"D": "deletes", "R": f"renames (to {f.path})"}.get(f.status, "modifies")
            raw.append(Finding("error", f"{action} {what}", path=f.base_path))
    for f in files:
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
    tip = branch_tip()
    lock = lock_commit(ctx.root, ctx.base, resolve_spec(ctx.root, ctx.branch, ctx.cfg), ctx.cfg, tip)
    since_lock = changed_files(ctx.root, lock, tip) if lock else []
    return check_test_tamper(changed_files(ctx.root, ctx.base), ctx.cfg, ctx.title, since_lock)


if __name__ == "__main__":
    main_for("check_test_tamper", __doc__.splitlines()[0], _run)
