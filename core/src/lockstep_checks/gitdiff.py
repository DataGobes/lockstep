"""Read a PR's changes from git: which files changed, how much, and which lines were added.

The diff is ``base...HEAD`` (from the merge base), which is what a reviewer sees in
the PR. Renames are detected so that renaming an existing test counts as touching it.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


class GitError(RuntimeError):
    """git failed, usually because the base branch is not fetched."""


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # A added, M modified, D deleted, R renamed, C copied, T type change
    old_path: str | None = None  # set for renames and copies
    added: int | None = 0  # None for binary files
    deleted: int | None = 0
    added_lines: tuple[tuple[int, str], ...] = field(default=(), repr=False)

    @property
    def existed_on_base(self) -> bool:
        return self.status != "A"

    @property
    def base_path(self) -> str:
        return self.old_path or self.path


def base_ref(arg: str | None, env: Mapping[str, str] | None = None) -> str:
    """The branch to diff against: --base, then the PR target in Azure Pipelines, then origin/main."""
    if arg:
        return arg
    env = os.environ if env is None else env
    target = env.get("SYSTEM_PULLREQUEST_TARGETBRANCH", "")
    if target:
        return "origin/" + target.removeprefix("refs/heads/")
    return "origin/main"


def changed_files(root: Path, base: str) -> list[ChangedFile]:
    spec = f"{base}...HEAD"
    statuses = _name_status(_git(root, "diff", "-M", "--name-status", "-z", spec))
    counts = _numstat(_git(root, "diff", "-M", "--numstat", "-z", spec))
    added = _added_lines(_git(root, "diff", "-M", "-U0", "--no-color", "--no-ext-diff", spec))
    files = []
    for path, (status, old_path) in statuses.items():
        a, d = counts.get(path, (0, 0))
        files.append(ChangedFile(path, status, old_path, a, d, tuple(added.get(path, ()))))
    return files


def _git(root: Path, *args: str) -> str:
    cmd = ["git", "-C", str(root), "-c", "core.quotePath=false", *args]
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GitError(f"cannot run git: {e}") from e
    if p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {p.stderr.strip()} (is the base branch fetched?)")
    return p.stdout


def _name_status(out: str) -> dict[str, tuple[str, str | None]]:
    parts = out.split("\0")
    result: dict[str, tuple[str, str | None]] = {}
    i = 0
    while i < len(parts) and parts[i]:
        code = parts[i][0]
        if code in "RC":
            result[parts[i + 2]] = (code, parts[i + 1])
            i += 3
        else:
            result[parts[i + 1]] = (code, None)
            i += 2
    return result


def _numstat(out: str) -> dict[str, tuple[int | None, int | None]]:
    parts = out.split("\0")
    result: dict[str, tuple[int | None, int | None]] = {}
    i = 0
    while i < len(parts) and parts[i]:
        a, d, path = parts[i].split("\t", 2)
        counts = (None, None) if a == "-" else (int(a), int(d))
        if path:
            i += 1
        else:  # rename: path is empty here and old/new follow as separate fields
            path = parts[i + 2]
            i += 3
        result[path] = counts
    return result


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _added_lines(out: str) -> dict[str, list[tuple[int, str]]]:
    result: dict[str, list[tuple[int, str]]] = {}
    path: str | None = None
    in_header = False  # between "diff --git" and the first hunk; "+++ " there is a file name, not content
    line_no = 0
    for line in out.splitlines():
        if line.startswith("diff --git"):
            in_header, path = True, None
            continue
        if in_header:
            if line.startswith("+++ "):
                target = line[4:]
                path = target[2:] if target.startswith("b/") else None  # /dev/null for deletions
            m = _HUNK.match(line)
            if not m:
                continue
            in_header = False
        m = _HUNK.match(line)
        if m:
            line_no = int(m.group(1))
            continue
        if path is None:
            continue
        if line.startswith("+"):
            result.setdefault(path, []).append((line_no, line[1:]))
            line_no += 1
        elif line.startswith(" "):
            line_no += 1
    return result
