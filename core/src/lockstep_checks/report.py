"""Print check findings for people and for Azure Pipelines.

In a pipeline (``TF_BUILD=True``) findings become ``##vso[task.logissue]`` commands,
so they show as errors and warnings on the PR with the file and line.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TextIO


@dataclass(frozen=True)
class Finding:
    level: Literal["error", "warning"]
    message: str
    path: str | None = None
    line: int | None = None


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
    if not findings:
        print(f"{check}: OK", file=out)
    return 1 if errors else 0


def _one_line(text: str) -> str:
    # Logging commands end at a newline; escape like the agent does.
    return text.replace("%", "%AZP25").replace("\r", "%0D").replace("\n", "%0A")
