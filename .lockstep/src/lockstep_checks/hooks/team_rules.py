"""PreToolUse on file edits and shell commands: apply the team's own rules from lockstep.toml.

Content rules check the text an edit would add to a file whose path they cover; command rules
check a shell command. Probity (github.com/nizos/probity) showed the value of rules a team writes
itself. These are plain regexes, so the hook stays deterministic and CI applies the same rules.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ..config import load_config
from ..rules import command_hits, content_hits
from . import Decision, Event, repo_root, run
from .guard_bash import SHELL_TOOLS, command_of
from .protect_tests import EDIT_TOOLS, file_root

_PATCH_HEAD = re.compile(r"^\*\*\* (?:Update|Add) File: (.+?)\s*$|^\+\+\+ (?:b/)?(.+?)\s*$")


def added_text(event: Event) -> list[tuple[str | None, list[str]]]:
    """(path, added lines) per file an edit writes; path None when the payload doesn't say."""
    args = event.tool_input
    path = next((str(args[k]) for k in ("file_path", "notebook_path", "path", "filePath") if args.get(k)), None)
    out: list[tuple[str | None, list[str]]] = []
    for key in ("content", "new_string", "newString", "file_text", "new_source"):
        if isinstance(args.get(key), str):
            out.append((path, args[key].splitlines()))
    for edit in args.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            out.append((path, edit["new_string"].splitlines()))
    for key in ("patch", "input", "diff"):  # apply_patch arrives as Edit with a patch body
        if isinstance(args.get(key), str):
            out += _patch_lines(args[key])
    return out


def _patch_lines(body: str) -> list[tuple[str | None, list[str]]]:
    files: list[tuple[str | None, list[str]]] = []
    for line in body.splitlines():
        m = _PATCH_HEAD.match(line)
        if m:
            files.append((m[1] or m[2], []))
        elif line.startswith("+") and files:
            files[-1][1].append(line[1:])
    return files


def hook(event: Event) -> Decision:
    if event.tool_name not in EDIT_TOOLS | SHELL_TOOLS:
        return Decision.allow()
    if event.tool_name in SHELL_TOOLS:
        cfg = load_config(repo_root(event.cwd))
        hits = [f"{r.name}: {r.message}" for r in command_hits(cfg, command_of(event))]
    else:
        hits = []
        for raw_path, lines in added_text(event):
            located = _locate(event.cwd, raw_path)
            if located is None:
                continue
            root, rel = located
            cfg = load_config(root)
            hits += [f"{r.name} ({rel}): {r.message}" for _, r in content_hits(cfg, rel, enumerate(lines, start=1))]
    if not hits:
        return Decision.allow()
    found = "; ".join(dict.fromkeys(hits))
    return Decision.deny(
        f"BLOCKED by lockstep: this breaks the team's rules in lockstep.toml: {found}. Change the approach rather "
        "than the wording. If the rule is wrong here, stop and ask the user."
    )


def _locate(cwd: Path, raw: str | None) -> tuple[Path, str] | None:
    """(repo root, repo-relative path) of the file an edit writes, judged from the file's own folder (protect_tests)."""
    if raw is None:
        return None
    p = Path(raw)
    p = (p if p.is_absolute() else cwd / p).resolve()
    root = file_root(p)
    return None if root is None else (root, p.relative_to(root).as_posix())


def main() -> None:
    sys.exit(run(hook))
