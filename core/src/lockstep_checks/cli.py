"""Shared command line for the PR checks: ``python -m lockstep_checks.check_<name>``.

The checks take ``lockstep.toml`` from the base branch, not from the PR: a PR that loosens the config (a gate set to
warn, a protect glob removed) is judged by the rules it would change, and the change itself needs the test reviewer
group (docs/branch-policy.md). Only when the base has no lockstep.toml yet (the PR that sets Lockstep up) is the PR's
own used.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import CONFIG_FILE, Config, ConfigError, load_config, parse_config
from .gitdiff import GitError, base_ref
from .report import Finding, apply_mode, emit
from .spec import SpecError, current_branch

TITLE_ENV = "LOCKSTEP_PR_TITLE"


@dataclass(frozen=True)
class PrContext:
    root: Path
    cfg: Config
    base: str
    branch: str | None
    title: str | None  # None when not given; Azure Pipelines has no built-in variable for it


def config_at(root: Path, base: str) -> Config:
    """The config as the base branch has it; the working tree's when there is no base or it has no lockstep.toml."""
    try:
        known = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{base}^{{commit}}"],
            check=False,
            capture_output=True,
            timeout=10,
        )
        shown = subprocess.run(
            ["git", "-C", str(root), "show", f"{base}:{CONFIG_FILE}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return load_config(root)
    if known.returncode != 0 or shown.returncode != 0:
        # No base to read (not fetched, or not a git repo: the diff checks then fail on their own), or the base has no
        # Lockstep config yet because this PR sets it up.
        return load_config(root)
    return parse_config(shown.stdout, Path(f"{base}:{CONFIG_FILE}"))


def run(check: str, description: str, fn: Callable[[PrContext], list[Finding]], argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"python -m lockstep_checks.{check}", description=description)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--base", help="branch to diff against (default: PR target branch, else origin/main)")
    ap.add_argument("--branch", help="PR source branch (default: from Azure Pipelines env or git)")
    ap.add_argument("--title", help=f"PR title (default: ${TITLE_ENV})")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        load_config(root)  # the PR's own config must still be valid
        base = base_ref(args.base)
        ctx = PrContext(
            root=root,
            cfg=config_at(root, base),
            base=base,
            branch=args.branch or current_branch(root),
            title=args.title if args.title is not None else os.environ.get(TITLE_ENV),
        )
        findings = apply_mode(fn(ctx), ctx.cfg.enforcement.mode(check))
    except (ConfigError, SpecError, GitError) as e:  # a broken config or spec fails in any mode
        findings = [Finding("error", str(e))]
    return emit(findings, check)


def main_for(check: str, description: str, fn: Callable[[PrContext], list[Finding]]) -> None:
    sys.exit(run(check, description, fn))
