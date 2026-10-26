"""Keep PRs small: warn above warn_lines, fail above fail_lines or max_files.

Generated files (``pr_size.ignore``) do not count towards lines. The file limit
counts every file, because it is Copilot code review's hard limit.
"""

from __future__ import annotations

from .cli import PrContext, main_for
from .config import Config
from .gitdiff import ChangedFile, changed_files
from .paths import matches_any
from .report import Finding

OVERRIDE = "[large-approved]"


def check_pr_size(files: list[ChangedFile], cfg: Config, title: str | None) -> list[Finding]:
    limits = cfg.pr_size
    counted = [f for f in files if not matches_any(f.path, limits.ignore)]
    lines = sum((f.added or 0) + (f.deleted or 0) for f in counted)
    findings = []
    if len(files) > limits.max_files:
        findings.append(
            Finding(
                "error", f"{len(files)} files changed; Copilot code review stops at {limits.max_files}. Split the PR."
            )
        )
    summary = f"{lines} changed lines (excluding {len(files) - len(counted)} generated files)"
    if lines > limits.fail_lines:
        if OVERRIDE in (title or ""):
            findings.append(Finding("warning", f"{summary}, above {limits.fail_lines}; allowed by {OVERRIDE}"))
        else:
            findings.append(
                Finding("error", f"{summary}, above {limits.fail_lines}. Split the PR or add {OVERRIDE} to its title.")
            )
    elif lines > limits.warn_lines:
        findings.append(Finding("warning", f"{summary}, above the {limits.warn_lines}-line target"))
    return findings


def _run(ctx: PrContext) -> list[Finding]:
    return check_pr_size(changed_files(ctx.root, ctx.base), ctx.cfg, ctx.title)


if __name__ == "__main__":
    main_for("check_pr_size", __doc__.splitlines()[0], _run)
