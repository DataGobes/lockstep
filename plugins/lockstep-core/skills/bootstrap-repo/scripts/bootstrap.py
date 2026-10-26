#!/usr/bin/env python3
"""Plan, then apply, the Lockstep files for a product repo.

  python3 bootstrap.py --root <repo>                      # print the plan, change nothing
  python3 bootstrap.py --root <repo> --diff               # also show diffs for files that differ
  python3 bootstrap.py --root <repo> --apply              # write the plan's create/update/remove actions

Lockstep owns `.lockstep/` (the shared core) and `specs/_template/`: they are created, updated and pruned to match the
source. Every other file belongs to the repo: it is created when missing and never overwritten. When it exists and
differs, the plan says "merge" and the skill merges it with the user.

The source is a Lockstep checkout (--source) or a git ref of the Lockstep repo (--ref, default main). Stdlib only.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GIT = "https://github.com/DataGobes/lockstep.git"
TRACKS = ("data", "ai")

# Source path -> repo path. Directories are copied whole, minus caches.
MANAGED = {
    "core/src/lockstep_checks": ".lockstep/src/lockstep_checks",
    "core/hooks": ".lockstep/hooks",
    "core/pipelines": ".lockstep/pipelines",
    "templates/specs/_template": "specs/_template",
}
REPO_OWNED = {
    "templates/lockstep.toml": "lockstep.toml",
    "templates/AGENTS.md": "AGENTS.md",
    "templates/CLAUDE.md": "CLAUDE.md",
    "templates/claude-settings.json": ".claude/settings.json",
    "templates/azuredevops/pull_request_template.md": ".azuredevops/pull_request_template.md",
    "templates/azure-pipelines-pr.yml": "azure-pipelines-pr.yml",
}
VERSION_FILE = ".lockstep/VERSION"
SKIP = {"__pycache__", ".pytest_cache", ".ruff_cache"}


@dataclass
class Action:
    path: str  # repo-relative, posix
    kind: str  # create | update | remove | same | merge
    content: bytes | None = None
    mode: int | None = None
    current: bytes | None = None

    def to_dict(self) -> dict:
        return {"path": self.path, "action": self.kind}


class BootstrapError(RuntimeError):
    pass


def fetch_source(git_url: str, ref: str, into: Path) -> tuple[Path, str]:
    try:
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", ref, git_url, str(into)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        sha = subprocess.run(
            ["git", "-C", str(into), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        detail = getattr(e, "stderr", "") or str(e)
        raise BootstrapError(f"cannot fetch Lockstep {ref} from {git_url}: {detail.strip()}") from e
    return into, sha


def local_commit(source: Path) -> str:
    p = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=False, capture_output=True, text=True)
    return p.stdout.strip() or "unknown"


def _files(src_dir: Path) -> dict[str, Path]:
    found = {}
    for p in sorted(src_dir.rglob("*")):
        if p.is_file() and not SKIP.intersection(p.relative_to(src_dir).parts) and p.suffix != ".pyc":
            found[p.relative_to(src_dir).as_posix()] = p
    return found


def customise_config(text: str, tracks: list[str], jira: list[str]) -> str:
    text = re.sub(r"^tracks = \[.*?\]", f"tracks = {json.dumps(tracks)}", text, count=1, flags=re.MULTILINE)
    return re.sub(r"^projects = \[.*?\]", f"projects = {json.dumps(jira)}", text, count=1, flags=re.MULTILINE)


def _compare(root: Path, rel: str, content: bytes, mode: int | None, owned_by_lockstep: bool) -> Action:
    dest = root / rel
    if not dest.exists():
        return Action(rel, "create", content, mode)
    current = dest.read_bytes()
    if current == content:
        return Action(rel, "same")
    return Action(rel, "update" if owned_by_lockstep else "merge", content, mode, current)


def plan(root: Path, source: Path, origin: str, tracks: list[str], jira: list[str]) -> list[Action]:
    missing = [s for s in [*MANAGED, *REPO_OWNED] if not (source / s).exists()]
    if missing:
        raise BootstrapError(f"{source} is not a Lockstep checkout; missing {', '.join(missing)}")
    actions: list[Action] = []
    for src, dest in MANAGED.items():
        wanted = _files(source / src)
        for rel, p in wanted.items():
            actions.append(_compare(root, f"{dest}/{rel}", p.read_bytes(), p.stat().st_mode & 0o777, True))
        for rel in sorted(set(_files(root / dest)) - set(wanted)) if (root / dest).is_dir() else []:
            actions.append(Action(f"{dest}/{rel}", "remove"))
    actions.append(_compare(root, VERSION_FILE, origin.encode(), None, True))
    for src, dest in REPO_OWNED.items():
        content = (source / src).read_bytes()
        if dest == "lockstep.toml":
            content = customise_config(content.decode(), tracks, jira).encode()
        actions.append(_compare(root, dest, content, None, False))
    return actions


def apply(root: Path, actions: list[Action]) -> None:
    for a in actions:
        dest = root / a.path
        if a.kind in ("create", "update"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(a.content or b"")
            if a.mode is not None:
                dest.chmod(a.mode)
        elif a.kind == "remove":
            dest.unlink()


def render(actions: list[Action], diff: bool) -> str:
    out = []
    for a in actions:
        if a.kind == "same":
            continue
        out.append(f"{a.kind:7} {a.path}")
        if diff and a.kind in ("update", "merge"):
            old = (a.current or b"").decode(errors="replace").splitlines(keepends=True)
            new = (a.content or b"").decode(errors="replace").splitlines(keepends=True)
            out.extend(
                line.rstrip("\n") for line in difflib.unified_diff(old, new, f"repo/{a.path}", f"lockstep/{a.path}")
            )
    same = sum(a.kind == "same" for a in actions)
    out.append(f"{same} file(s) already up to date")
    return "\n".join(out)


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="product repo root (default: current directory)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--source", type=Path, help="a local Lockstep checkout to copy from")
    src.add_argument("--ref", default="main", help="Lockstep tag or branch to fetch (default: main)")
    ap.add_argument("--git", default=DEFAULT_GIT, help=f"Lockstep git URL (default: {DEFAULT_GIT})")
    ap.add_argument("--tracks", type=_list, default=list(TRACKS), help="comma-separated: data, ai (default: both)")
    ap.add_argument("--jira", type=_list, default=["MXAAI"], help="comma-separated Jira project keys (default: MXAAI)")
    ap.add_argument("--diff", action="store_true", help="show diffs for files that differ")
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    ap.add_argument("--apply", action="store_true", help="write create, update and remove actions")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    bad = [t for t in args.tracks if t not in TRACKS]
    if bad or not args.tracks:
        ap.error(f"--tracks must be some of {', '.join(TRACKS)}")
    if not all(re.fullmatch(r"[A-Z][A-Z0-9_]+", k) for k in args.jira) or not args.jira:
        ap.error("--jira takes upper-case project keys such as MXAAI")
    if not (root / ".git").exists():
        ap.error(f"{root} is not a git repo root")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            if args.source:
                source = args.source.resolve()
                origin = f"source: {source}\ncommit: {local_commit(source)}\n"
            else:
                source, sha = fetch_source(args.git, args.ref, Path(tmp) / "lockstep")
                origin = f"source: {args.git}@{args.ref}\ncommit: {sha}\n"
            actions = plan(root, source, origin, args.tracks, args.jira)
            if args.apply:
                apply(root, actions)
    except BootstrapError as e:
        print(f"bootstrap: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([a.to_dict() for a in actions if a.kind != "same"], indent=2))
    else:
        print(render(actions, args.diff))
        if args.apply:
            print("applied create, update and remove actions; merge actions are left for you")
    return 0


if __name__ == "__main__":
    sys.exit(main())
