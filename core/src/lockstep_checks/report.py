"""Print check findings for people and for Azure Pipelines.

In a pipeline (``TF_BUILD=True``) findings become ``##vso[task.logissue]`` commands,
so they show as errors and warnings on the PR with the file and line, and the run is
tagged ``lockstep-blocked-<check>`` or ``lockstep-would-block-<check>`` so the team can
count, across PRs, how often each check fired.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Literal, TextIO


@dataclass(frozen=True)
class Finding:
    level: Literal["error", "warning"]
    message: str
    path: str | None = None
    line: int | None = None
    would_block: bool = False  # an error downgraded by warn mode


def apply_mode(findings: Iterable[Finding], mode: str) -> list[Finding]:
    """In warn mode, report each error as a warning that says it would have blocked."""
    if mode == "enforce":
        return list(findings)
    return [
        replace(f, level="warning", message=f"would block (warn mode): {f.message}", would_block=True)
        if f.level == "error"
        else f
        for f in findings
    ]


def emit(
    findings: Iterable[Finding], check: str, env: Mapping[str, str] | None = None, out: TextIO | None = None
) -> int:
    """Print findings and return the exit code: 1 if any error, else 0."""
    env = os.environ if env is None else env
    out = sys.stdout if out is None else out
    in_pipeline = env.get("TF_BUILD", "").lower() == "true"
    findings = list(findings)
    for f in findings:
        if in_pipeline:
            props = f"type={f.level}"
            if f.path:
                props += f";sourcepath={f.path}"
            if f.line:
                props += f";linenumber={f.line}"
            print(f"##vso[task.logissue {props}]{check}: {_one_line(f.message)}", file=out)
        else:
            where = f"{f.path}:{f.line}: " if f.path and f.line else f"{f.path}: " if f.path else ""
            print(f"{f.level.upper()} {check}: {where}{f.message}", file=out)
    errors = sum(f.level == "error" for f in findings)
    if in_pipeline:
        name = check.removeprefix("check_")
        if errors:
            print(f"##vso[build.addbuildtag]lockstep-blocked-{name}", file=out)
        if any(f.would_block for f in findings):
            print(f"##vso[build.addbuildtag]lockstep-would-block-{name}", file=out)
    if not findings:
        print(f"{check}: OK", file=out)
    return 1 if errors else 0


def _one_line(text: str) -> str:
    # Logging commands end at a newline; escape like the agent does.
    return text.replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")
