"""PreToolUse on file edits: once the active spec is tests-locked, existing tests are read-only.

A file is protected when it matches ``[protect] globs`` and already exists on the base
branch (origin/main) or, on a feature branch, at the commit where the test PR locked the
spec's tests (lock.py). New test files stay allowed. On a branch without a spec the edit
is allowed with a warning; CI's check_test_tamper is the backstop either way.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

from ..config import load_config
from ..gitdiff import base_ref
from ..lock import lock_commit
from ..paths import matches_any
from ..spec import SpecError, current_branch, resolve_spec
from . import Decision, Event, repo_root, run
from .guard_bash import SHELL_TOOLS, command_of

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Shell commands that write, move or delete the files they name. Such a command that names a locked test counts as an
# edit of it, so `sed -i` or `cat > tests/...` can't do what the Edit tool may not. Commands that only read files they
# name (pytest, cat, git diff) are not affected; their output redirect is.
_SEGMENT = re.compile(r"\|\||&&|[;|&\n]")
_REDIRECT = re.compile(r"(?:^|[^<>&\d])\d?>>?\s*([^\s;&|<>]+)")
_WRITES_ALL = {"rm", "mv", "truncate", "tee", "unlink", "shred", "Remove-Item", "Move-Item", "Set-Content", "Out-File"}
_WRITES_LAST = {"cp", "install", "Copy-Item"}
_GIT_WRITES = {"rm", "mv", "checkout", "restore", "apply"}
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


def file_root(path: Path) -> Path | None:
    """The repo a file belongs to, from its own folder, or None outside any repo. The implement skill's worktree sits
    next to the repo the agent was started in, so the session's cwd names the wrong repo for its files."""
    folder = path.parent
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent  # a new file in a new folder
    root = repo_root(folder)
    return root.resolve() if (root / ".git").exists() else None


def shell_paths(command: str) -> list[str]:
    """The files a shell command would write, move or delete: redirect targets and the file arguments of writing
    commands. A command that only reads the files it names (pytest, cat, git diff) gives none."""
    out = []
    for segment in _SEGMENT.split(command):
        out += _REDIRECT.findall(segment)
        try:
            words = shlex.split(_REDIRECT.sub(" ", segment))
        except ValueError:
            words = segment.split()
        while words and (words[0] in ("sudo", "env", "command") or "=" in words[0]):
            words = words[1:]
        if not words:
            continue
        cmd, args = words[0].rsplit("/", 1)[-1], [w for w in words[1:] if not w.startswith("-")]
        if cmd == "git" and args and args[0] in _GIT_WRITES:
            out += args[1:]
        elif cmd in _WRITES_ALL or (cmd in ("sed", "perl") and any(re.match(r"-[a-zA-Z]*i", w) for w in words)):
            out += args[1:] if cmd in ("sed", "perl") else args  # sed's first argument is the script
        elif cmd in _WRITES_LAST and args:
            out.append(args[-1])
        elif cmd == "dd":
            out += [w[3:] for w in words if w.startswith("of=")]
    return out


def hook(event: Event) -> Decision:
    if event.tool_name in SHELL_TOOLS:
        paths = shell_paths(command_of(event))
    elif event.tool_name in EDIT_TOOLS:
        paths = target_paths(event)
    else:
        return Decision.allow()
    by_root: dict[Path, list[str]] = {}
    for raw_path in paths:
        p = Path(raw_path)
        p = p if p.is_absolute() else event.cwd / p
        root = file_root(p.resolve())
        if root is None:
            continue  # not in a git repo
        rel = p.resolve().relative_to(root).as_posix()
        by_root.setdefault(root, []).append(rel)
    warnings: list[str] = []
    for root, rels in by_root.items():
        decision = _check(root, rels)
        if decision.block:
            return decision
        warnings += decision.warnings
    return Decision.allow(*warnings)


def _check(root: Path, rels: list[str]) -> Decision:
    cfg = load_config(root)
    protected = [rel for rel in rels if matches_any(rel, cfg.protect.globs)]
    if not protected:
        return Decision.allow()

    branch = current_branch(root, env={})  # the checkout's branch, also when an agent runs inside CI
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
    # An implemented spec's tests are locked on every branch. Its locked_at_commit still says which, when the base
    # doesn't have them yet and no lock commit is on this branch's first parents (work merged in from another remote).
    pinned = spec.status.locked_at_commit if spec.status.status == "implemented" else None
    warnings = []
    existing = []
    for rel in protected:
        on_base = _exists_on(root, base, rel)
        if on_base is None:
            on_base = _exists_on(root, "HEAD", rel)
            warnings.append(f"{base} is not fetched; judged {rel} against HEAD instead")
        if on_base or (lock and _exists_on(root, lock, rel)) or (pinned and _exists_on(root, pinned, rel)):
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
