"""Shared command line for the PR checks: ``python -m lockstep_checks.check_<name>``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Config, ConfigError, load_config
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


def run(check: str, description: str, fn: Callable[[PrContext], list[Finding]], argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"python -m lockstep_checks.{check}", description=description)
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--base", help="branch to diff against (default: PR target branch, else origin/main)")
    ap.add_argument("--branch", help="PR source branch (default: from Azure Pipelines env or git)")
    ap.add_argument("--title", help=f"PR title (default: ${TITLE_ENV})")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        ctx = PrContext(
            root=root,
            cfg=load_config(root),
            base=base_ref(args.base),
            branch=args.branch or current_branch(root),
            title=args.title if args.title is not None else os.environ.get(TITLE_ENV),
        )
        findings = apply_mode(fn(ctx), ctx.cfg.enforcement.mode(check))
    except (ConfigError, SpecError, GitError) as e:  # a broken config or spec fails in any mode
        findings = [Finding("error", str(e))]
    return emit(findings, check)


def main_for(check: str, description: str, fn: Callable[[PrContext], list[Finding]]) -> None:
    sys.exit(run(check, description, fn))
