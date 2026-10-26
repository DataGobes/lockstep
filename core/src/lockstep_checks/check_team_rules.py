"""Fail a PR that adds code a team rule forbids (``[[rules]]`` with ``on = "content"`` in lockstep.toml).

Only added lines count, so existing code that breaks a new rule doesn't block unrelated work.
Command rules are checked by the team_rules hook only: a PR diff holds no commands.
"""

from __future__ import annotations

from .cli import PrContext, main_for
from .config import Config
from .gitdiff import ChangedFile, changed_files
from .report import Finding
from .rules import content_hits


def check_team_rules(files: list[ChangedFile], cfg: Config) -> list[Finding]:
    findings = []
    for f in files:
        for line, rule in content_hits(cfg, f.path, f.added_lines):
            findings.append(Finding("error", f"rule {rule.name}: {rule.message}", f.path, line))
    return findings


def _run(ctx: PrContext) -> list[Finding]:
    if not any(r.on == "content" for r in ctx.cfg.rules):
        return []
    return check_team_rules(changed_files(ctx.root, ctx.base), ctx.cfg)


if __name__ == "__main__":
    main_for("check_team_rules", __doc__.splitlines()[0], _run)
