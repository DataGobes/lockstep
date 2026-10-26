"""Fail a PR that changes existing tests or quietly weakens checks.

Existing files under ``protect.globs`` (tests, dbt unit-test YAML, eval thresholds and
datasets, snapshots) may not be modified, renamed or deleted, and no change may add
skip/xfail markers, disabled or downgraded dbt tests, ``# noqa`` or ``type: ignore``.
New test files are fine. A PR whose title starts with ``[test-change]`` is a deliberate
test change: findings are reported as warnings and the required reviewer decides.

On a feature branch the spec's own tests are new to main but locked since the test PR merged
into the branch (lock.py), so changes to them since that commit fail too.

On a baseline branch an existing test may be adopted: a change that only adds criterion tags
(``@pytest.mark.ac("0042/AC-001")``, ``meta: {ac: 0042/AC-001}``, ``import pytest``) and removes
nothing lets a baseline spec point at tests the repo already has.
"""

from __future__ import annotations

import re

from .cli import PrContext, main_for
from .config import CONFIG_FILE, Config
from .gitdiff import ChangedFile, changed_files
from .lock import branch_tip, lock_commit
from .paths import matches, matches_any
from .report import Finding
from .spec import resolve_spec

OVERRIDE = "[test-change]"
# The vendored core (bootstrap-repo copies it): its own source names the markers it looks for. Changes to it need the
# test reviewer group, by branch policy.
VENDORED = ".lockstep/**"
ADOPT_BRANCH = "baseline/"

_REF = r"\d+/AC-\d+"
# Lines that tag an existing test with a criterion and change nothing it checks. Not `config:`: a second one in a
# YAML mapping replaces the first, dropping its settings.
_TAG_LINES = tuple(
    re.compile(pattern)
    for pattern in (
        rf"^\s*@pytest\.mark\.ac\(\s*(?:['\"]{_REF}['\"]\s*,?\s*)+\)\s*$",
        rf"^\s*pytestmark\s*=\s*\[?\s*pytest\.mark\.ac\(\s*(?:['\"]{_REF}['\"]\s*,?\s*)+\)\s*\]?\s*$",
        r"^\s*import pytest\s*$",
        rf"^\s*(?:-\s*)?meta:\s*\{{\s*ac:\s*['\"]?{_REF}['\"]?\s*\}}\s*$",
        r"^\s*$",
    )
)

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


def adopts_only(f: ChangedFile) -> bool:
    """True if the change only tags an existing test with criteria: tag lines added, nothing removed."""
    lines = [text for _, text in f.added_lines]
    return (
        f.status == "M"
        and f.deleted == 0
        and any(text.strip() and "AC-" in text for text in lines)
        and all(any(p.match(text) for p in _TAG_LINES) for text in lines)
    )


def check_test_tamper(
    files: list[ChangedFile],
    cfg: Config,
    title: str | None,
    since_lock: list[ChangedFile] = (),
    branch: str | None = None,
) -> list[Finding]:
    """``files`` is the PR's diff; ``since_lock`` the diff since the spec's lock commit, on a feature branch."""
    protected = cfg.protect.globs
    raw: list[Finding] = []
    adopting = (branch or "").startswith(ADOPT_BRANCH)
    touched = [(f, "an existing test or eval file") for f in files if not (adopting and adopts_only(f))]
    touched += [(f, "a locked test") for f in since_lock]
    seen = set()
    for f, what in touched:
        # copying a test leaves the original intact
        if f.existed_on_base and f.status != "C" and matches_any(f.base_path, protected) and f.base_path not in seen:
            seen.add(f.base_path)
            action = {"D": "deletes", "R": f"renames (to {f.path})"}.get(f.status, "modifies")
            raw.append(Finding("error", f"{action} {what}", path=f.base_path))
    for f in files:
        if matches(f.path, VENDORED):
            continue
        for line_no, text in f.added_lines:
            for suffixes, pattern, label in _WEAKENERS:
                if f.path.endswith(suffixes) and pattern.search(text):
                    raw.append(Finding("error", f"added line {label}: {text.strip()}", path=f.path, line=line_no))
                    break
    if any(f.path == CONFIG_FILE for f in files):
        raw.append(
            Finding(
                "warning",
                f"this PR changes {CONFIG_FILE}; the checks keep using the target branch's until it merges, and the "
                "test reviewer group must approve it",
                path=CONFIG_FILE,
            )
        )
    if raw and (title or "").startswith(OVERRIDE):
        return [Finding("warning", f"{x.message} (allowed by {OVERRIDE})", x.path, x.line) for x in raw]
    if any(x.level == "error" for x in raw):
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
    return check_test_tamper(changed_files(ctx.root, ctx.base), ctx.cfg, ctx.title, since_lock, ctx.branch)


if __name__ == "__main__":
    main_for("check_test_tamper", __doc__.splitlines()[0], _run)
