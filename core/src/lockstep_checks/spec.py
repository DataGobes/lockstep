"""Find the spec a branch works on: branch name -> ``specs/<id>-<slug>/`` -> status.yml.

Every hook, skill and CI check asks this module which spec is active, so the
rule lives in one place. Run ``python -m lockstep_checks.spec`` to see the answer as
JSON, which is also how the bash hook shims read it.

States:
  found     the branch names a spec id and its folder exists
  no-match  the branch names no spec id (main, chore branches)
  missing   the branch names an id but no folder exists yet
A broken spec (two folders for one id, missing or invalid status.yml) raises
SpecError: callers must fail loudly rather than treat it as "no spec".
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import ci
from .config import Config, ConfigError, load_config
from .status import SpecStatus, SpecStatusError, parse_status

STATUS_FILE = "status.yml"


class SpecError(ValueError):
    """The branch points at a spec that is broken."""


@dataclass(frozen=True)
class Resolution:
    state: Literal["found", "no-match", "missing"]
    branch: str | None
    spec_id: str | None = None
    spec_dir: Path | None = None
    status: SpecStatus | None = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "branch": self.branch,
            "spec_id": self.spec_id,
            "spec_dir": str(self.spec_dir) if self.spec_dir else None,
            "status": self.status.to_dict() if self.status else None,
        }


def current_branch(root: Path, env: Mapping[str, str] | None = None) -> str | None:
    # CI first: in a PR build HEAD is a detached merge commit.
    branch = ci.source_branch(env)
    if branch:
        return branch
    try:
        p = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() or None


def resolve_spec(root: Path, branch: str | None, cfg: Config) -> Resolution:
    m = cfg.branch_regex.match(branch or "")
    if not m:
        return Resolution(state="no-match", branch=branch)
    spec_id = m["id"]
    specs = Path(root) / cfg.specs_dir
    folders = sorted(p for p in specs.glob(f"{spec_id}-*") if p.is_dir()) if specs.is_dir() else []
    if not folders:
        return Resolution(state="missing", branch=branch, spec_id=spec_id)
    if len(folders) > 1:
        names = ", ".join(p.name for p in folders)
        raise SpecError(f"spec id {spec_id} has more than one folder: {names}")

    spec_dir = folders[0]
    return Resolution(
        state="found", branch=branch, spec_id=spec_id, spec_dir=spec_dir, status=load_status(root, spec_dir, cfg)
    )


def load_status(root: Path, spec_dir: Path, cfg: Config) -> SpecStatus:
    status_path = spec_dir / STATUS_FILE
    rel = status_path.relative_to(root) if status_path.is_relative_to(root) else status_path
    try:
        text = status_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SpecError(f"{rel} is missing") from None
    try:
        return parse_status(text, cfg)
    except SpecStatusError as e:
        raise SpecError(f"{rel}: {e}") from e


def list_specs(root: Path, cfg: Config) -> dict[str, Path]:
    """Every spec folder (``<id>-<slug>``) by id. ``_template`` and other folders are skipped."""
    specs = Path(root) / cfg.specs_dir
    found: dict[str, Path] = {}
    for p in sorted(specs.iterdir()) if specs.is_dir() else []:
        m = re.match(r"(\d+)-", p.name)
        if not (p.is_dir() and m):
            continue
        if m[1] in found:
            raise SpecError(f"spec id {m[1]} has more than one folder: {found[m[1]].name}, {p.name}")
        found[m[1]] = p
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lockstep_checks.spec", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--branch", help="branch name (default: from Azure Pipelines env or git)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        cfg = load_config(root)
        branch = args.branch or current_branch(root)
        result = resolve_spec(root, branch, cfg)
    except (ConfigError, SpecError) as e:
        print(f"lockstep_checks: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
