"""PreToolUse on file edits: once the active spec is tests-locked, existing tests are read-only.

A file is protected when it matches ``[protect] globs`` and already exists on the base
branch (origin/main) or, on a feature branch, at the commit where the test PR locked the
spec's tests (lock.py). New test files stay allowed. On a branch without a spec the edit
is allowed with a warning; CI's check_test_tamper is the backstop either way.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from ..config import load_config
from ..gitdiff import base_ref
from ..lock import lock_commit
from ..paths import matches_any
from ..spec import SpecError, current_branch, resolve_spec
from . import Decision, Event, repo_root, run

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.MULTILINE)
_DIFF_FILE = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(.+?)\s*$", re.MULTILINE)


def target_paths(event: Event) -> list[str]:
    """Every file the tool call would write, from Claude's and Copilot's argument shapes."""
    args = event.tool_input
    paths = [str(args[k]) for k in ("file_path", "notebook_path", "path", "filePath") if args.get(k)]
    for key in ("patch", "input", "diff"):  # apply_patch arrives as Edit with a patch body
        body = args.get(key)
        if isinstance(body, str):
            paths += [a or b for a, b in _PATCH_FILE.findall(body)]
            paths += [p for p in _DIFF_FILE.findall(body) if p != "/dev/null"]
    return list(dict.fromkeys(paths))


def _exists_on(root: Path, ref: str, rel: str) -> bool | None:
    """True/False if ``ref`` is known, None if it cannot be read (not fetched)."""
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{ref}:{rel}"],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if p.returncode == 0:
            return True
        known = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "-q", ref],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return False if known.returncode == 0 else None


def hook(event: Event) -> Decision:
    if event.tool_name not in EDIT_TOOLS:
        return Decision.allow()
    root = repo_root(event.cwd)
    cfg = load_config(root)
    protected = []
    for raw_path in target_paths(event):
        p = Path(raw_path)
        p = p if p.is_absolute() else event.cwd / p
        try:
            rel = p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue  # outside the repo
        if matches_any(rel, cfg.protect.globs):
            protected.append(rel)
    if not protected:
        return Decision.allow()

    branch = current_branch(root)
    try:
        spec = resolve_spec(root, branch, cfg)
    except SpecError as e:
        return Decision.deny(f"BLOCKED by lockstep: the active spec is broken ({e}). Fix it before editing tests.")
    if spec.state != "found":
        return Decision.allow(f"no spec for branch {branch!r}; test edits are not locked here (CI still checks them)")
    if not spec.status.tests_locked:
        return Decision.allow()

    base = base_ref(None)
    lock = lock_commit(root, base, spec, cfg)
    warnings = []
    existing = []
    for rel in protected:
        on_base = _exists_on(root, base, rel)
        if on_base is None:
            on_base = _exists_on(root, "HEAD", rel)
            warnings.append(f"{base} is not fetched; judged {rel} against HEAD instead")
        if on_base or (lock and _exists_on(root, lock, rel)):
            existing.append(rel)
    if not existing:
        return Decision.allow(*warnings)
    files = ", ".join(existing)
    return Decision.deny(
        f"BLOCKED by lockstep: {files} existed before spec {spec.spec_id} was tests-locked, so it must not change. "
        "Do not edit, weaken, skip or work around this test. If you believe the test is wrong, stop and explain "
        "why to the user. A real test change goes in a separate PR titled '[test-change] ...'. "
        "Adding new test files is allowed."
    )


def main() -> None:
    sys.exit(run(hook))
