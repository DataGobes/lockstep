"""Print check findings for people, for Azure Pipelines and for GitHub Actions.

In Azure Pipelines (``TF_BUILD=True``) findings become ``##vso[task.logissue]`` commands,
so they show as errors and warnings on the PR with the file and line, and the run is
tagged ``lockstep-blocked-<check>`` or ``lockstep-would-block-<check>`` so the team can
count, across PRs, how often each check fired. GitHub Actions (``GITHUB_ACTIONS=true``) gets
``::error``/``::warning`` annotations instead, and a ``::notice`` titled with the same tag, since a
run there has no tags. With ``LOCKSTEP_EVIDENCE_DIR`` set, each check's findings also go to
the ``checks`` evidence file the trust summary reads.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from typing import Literal, TextIO

from . import ci
from .evidence import evidence_dir, record_check


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
    out = sys.stdout if out is None else out
    in_pipeline, on_github = ci.on_azure(env), ci.on_github(env)
    findings = list(findings)
    for f in findings:
        if on_github:
            props = f"file={_gh_prop(f.path)}" if f.path else ""
            if f.path and f.line:
                props += f",line={f.line}"
            props += f"{',' if props else ''}title=lockstep {check}"
            print(f"::{f.level} {props}::{_gh_data(f.message)}", file=out)
        elif in_pipeline:
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
    folder = evidence_dir(env)
    if folder is not None and check.startswith("check_"):
        record_check(folder, check, [asdict(f) for f in findings])
    name = check.removeprefix("check_")
    tags = [f"lockstep-blocked-{name}"] if errors else []
    tags += [f"lockstep-would-block-{name}"] if any(f.would_block for f in findings) else []
    for tag in tags:
        if in_pipeline:
            print(f"##vso[build.addbuildtag]{tag}", file=out)
        elif on_github:
            print(f"::notice title={tag}::{check} fired", file=out)
    if not findings:
        print(f"{check}: OK", file=out)
    return 1 if errors else 0


def _one_line(text: str) -> str:
    # Logging commands end at a newline; escape like the agent does.
    return text.replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_data(text: str) -> str:
    # GitHub workflow commands end at a newline; escape like the runner does.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_prop(text: str) -> str:
    return _gh_data(text).replace(":", "%3A").replace(",", "%2C")
