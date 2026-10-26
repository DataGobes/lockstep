"""Fail a PR that changes code without a spec, unless it is a chore or a bugfix.

Spec-first only holds if CI enforces it: the ``implement`` skill checks the spec
locally, but only when the agent uses it. Changes under ``[lanes] no_spec_needed``
(specs, docs) never need one. Any other change must be on one of these lanes:

  feature/<id>-   the spec is tests-locked (or implemented)
  test/<id>-      the spec is approved or tests-locked; the test PR adds stubs and merges into feature/<id>-.
                  The spec must have had its own spec PR, unless it is small enough for the quick lane
                  ([specs] quick_max_criteria): then it may arrive in the test PR, reviewed with its tests.
  spec/<id>-      specs and docs only; code waits for the test PR
  bugfix/, hotfix/  a bug report under ``bug_reports_dir`` and a new regression test
  chore/          no spec; dependency bumps, config and tooling, no behaviour change

The chore exemption and the bug lane follow SDTRD (Fast-Track Protocol, Gates B1 to B3).
"""

from __future__ import annotations

from .cli import PrContext, main_for
from .config import Config
from .gitdiff import ChangedFile, changed_files
from .paths import matches, matches_any
from .report import Finding
from .spec import Resolution, resolve_spec
from .specdoc import parse_spec
from .status import LOCKED_STATES

_ALLOWED = {"test": ("approved", "tests-locked"), "feature": LOCKED_STATES}


def check_spec_required(files: list[ChangedFile], branch: str | None, spec: Resolution, cfg: Config) -> list[Finding]:
    lanes = cfg.lanes
    code = [f.path for f in files if f.status != "D" and not matches_any(f.path, lanes.no_spec_needed)]
    if not code:
        return []
    branch = branch or ""
    first = code[0] + (f" and {len(code) - 1} more" if len(code) > 1 else "")
    if branch.startswith(lanes.chore):
        return []
    if branch.startswith(lanes.bugfix):
        return _bug_lane(files, cfg)
    if spec.state == "no-match":
        lane_list = ", ".join((*lanes.bugfix, *lanes.chore))
        return [
            Finding(
                "error",
                f"changes code ({first}) on a branch with no spec. Use feature/<id>- for a tests-locked spec, "
                f"or one of {lane_list} for a bug or a chore",
            )
        ]
    if spec.state == "missing":
        return [
            Finding("error", f"branch names spec {spec.spec_id} but {cfg.specs_dir}/{spec.spec_id}-*/ does not exist")
        ]
    kind = branch.split("/", 1)[0]
    status = spec.status.status if spec.status else None
    where = f"{cfg.specs_dir}/{spec.spec_dir.name}/status.yml" if spec.spec_dir else None
    if kind == "spec":
        return [Finding("error", f"a spec PR changes only specs and docs; {first} belongs in the test or feature PR")]
    allowed = _ALLOWED.get(kind, _ALLOWED["feature"])
    if status not in allowed:
        return [
            Finding(
                "error",
                f"spec {spec.spec_id} is {status}; a {kind} PR that changes code needs it {' or '.join(allowed)}",
                path=where,
            )
        ]
    if kind == "test" and spec.spec_dir is not None:
        return _quick_lane(files, spec, cfg)
    return []


def _quick_lane(files: list[ChangedFile], spec: Resolution, cfg: Config) -> list[Finding]:
    """A test PR that adds its own spec skipped the spec PR: allowed only for small specs, when the repo allows it."""
    md = spec.spec_dir / "spec.md"
    rel = f"{cfg.specs_dir}/{spec.spec_dir.name}/spec.md"
    if not any(f.path == rel and f.status == "A" for f in files):
        return []
    limit = cfg.specs.quick_max_criteria
    if limit == 0:
        why = "this repo has no quick lane ([specs] quick_max_criteria = 0)"
    elif spec.status and spec.status.design:
        why = "it takes the research and design step"
    else:
        try:
            count = len(parse_spec(md.read_text(encoding="utf-8"), cfg.specs.ac_format).criteria)
        except OSError:
            return []  # the traceability check reports a missing spec.md
        if count <= limit:
            return []
        why = f"it has {count} criteria and the quick lane takes at most {limit}"
    return [
        Finding(
            "error",
            f"spec {spec.spec_id} arrives in this test PR without a spec PR of its own, but {why}. Open the spec PR "
            "first, then the test PR",
            path=rel,
        )
    ]


def _bug_lane(files: list[ChangedFile], cfg: Config) -> list[Finding]:
    reports = cfg.lanes.bug_reports_dir.rstrip("/")
    findings = []
    # _template.md is the blank template, not a report.
    is_report = [matches(f.path, f"{reports}/*.md") and not f.path.endswith("/_template.md") for f in files]
    if not any(f.status != "D" and ok for f, ok in zip(files, is_report, strict=True)):
        findings.append(
            Finding("error", f"a bugfix PR needs its bug report: add {reports}/<KEY>-<slug>.md from the template")
        )
    if not any(f.status == "A" and matches_any(f.path, cfg.protect.globs) for f in files):
        findings.append(Finding("error", "a bugfix PR needs a new regression test file that failed before the fix"))
    return findings


def _run(ctx: PrContext) -> list[Finding]:
    files = changed_files(ctx.root, ctx.base)
    return check_spec_required(files, ctx.branch, resolve_spec(ctx.root, ctx.branch, ctx.cfg), ctx.cfg)


if __name__ == "__main__":
    main_for("check_spec_required", __doc__.splitlines()[0], _run)
