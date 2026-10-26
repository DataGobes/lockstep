"""Require a Jira issue key in the PR title or branch, matching the spec's ``jira`` key.

Azure DevOps' linked-work-item policy only covers Azure Boards, so this check is
how a PR is tied to its Jira issue.
"""

from __future__ import annotations

from .cli import PrContext, main_for
from .config import Config
from .report import Finding
from .spec import Resolution, resolve_spec


def check_jira_key(title: str | None, branch: str | None, spec: Resolution, cfg: Config) -> list[Finding]:
    keys: list[str] = []
    for text in (title or "", branch or ""):
        for m in cfg.jira_key_regex.finditer(text):
            if m.group() not in keys:
                keys.append(m.group())
    example = f"{cfg.jira_projects[0]}-123"
    findings = []
    if title is None:
        findings.append(
            Finding("warning", "PR title not given (--title or LOCKSTEP_PR_TITLE); checked the branch only")
        )
    if not keys:
        projects = "/".join(cfg.jira_projects)
        findings.append(Finding("error", f"no {projects} issue key in the PR title or branch; add one, e.g. {example}"))
        return findings
    if len(keys) > 1 and not cfg.jira_multiple_keys:
        findings.append(Finding("error", f"more than one issue key ({', '.join(keys)}); one PR should serve one issue"))
    spec_key = spec.status.jira if spec.status else None
    if spec_key and spec_key not in keys:
        findings.append(
            Finding(
                "error",
                f"PR names {', '.join(keys)} but spec {spec.spec_id} is for {spec_key}",
                path=f"{spec.spec_dir.name}/status.yml" if spec.spec_dir else None,
            )
        )
    return findings


def _run(ctx: PrContext) -> list[Finding]:
    return check_jira_key(ctx.title, ctx.branch, resolve_spec(ctx.root, ctx.branch, ctx.cfg), ctx.cfg)


if __name__ == "__main__":
    main_for("check_jira_key", __doc__.splitlines()[0], _run)
