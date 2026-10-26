"""Evidence files: what each PR job measured, for the trust summary (spec 0001).

A job writes ``<dir>/<producer>.json`` when ``LOCKSTEP_EVIDENCE_DIR`` is set, and publishes the folder as a pipeline
artifact. Producers never know how the summary looks; the summary never knows how a signal was measured.

  python -m lockstep_checks.evidence coverage --report diff-cover.json --minimum 80

adds diff-cover's changed-line coverage to the quality evidence. The other producers write their own: the checks
through ``report.emit``, pytest through the ``lockstep_checks.pytest_evidence`` plugin, and the mutation report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DIR_ENV = "LOCKSTEP_EVIDENCE_DIR"


def evidence_dir(env: Mapping[str, str] | None = None) -> Path | None:
    env = os.environ if env is None else env
    value = env.get(DIR_ENV, "")
    return Path(value) if value else None


def read(folder: Path, producer: str) -> dict[str, Any]:
    path = folder / f"{producer}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or data.get("producer") != producer:
        data = {"schema_version": SCHEMA_VERSION, "producer": producer, "status": "measured", "reason": None}
    data.setdefault("signals", {})
    return data


def write(folder: Path, data: dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{data['producer']}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def update(folder: Path, producer: str, signals: dict[str, Any]) -> Path:
    """Merge ``signals`` into the producer's file, keeping what other steps of the same job wrote."""
    data = read(folder, producer)
    data["signals"].update(signals)
    return write(folder, data)


def not_measured(folder: Path, producer: str, status: str, reason: str) -> Path:
    data = {"schema_version": SCHEMA_VERSION, "producer": producer, "status": status, "reason": reason, "signals": {}}
    return write(folder, data)


def record_check(folder: Path, check: str, findings: list[dict[str, Any]]) -> Path:
    data = read(folder, "checks")
    data["signals"].setdefault("checks", {})[check.removeprefix("check_")] = {"findings": findings}
    return write(folder, data)


def coverage_from_diff_cover(report: Mapping[str, Any], minimum: float) -> dict[str, Any] | None:
    """diff-cover's JSON report -> the coverage signal; None when the PR changed no measured lines."""
    percent = report.get("total_percent_covered")
    if percent is None or not report.get("total_num_lines"):
        return None
    return {"percent": float(percent), "minimum": minimum}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lockstep_checks.evidence", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    cov = sub.add_parser("coverage", help="add changed-line coverage from a diff-cover JSON report")
    cov.add_argument("--report", type=Path, required=True)
    cov.add_argument("--minimum", type=float, required=True)
    args = ap.parse_args(argv)
    folder = evidence_dir()
    if folder is None:
        print(f"lockstep_checks.evidence: {DIR_ENV} is not set, nothing written", file=sys.stderr)
        return 0
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"lockstep_checks.evidence: cannot read {args.report}: {e}", file=sys.stderr)
        return 0  # the summary then shows coverage as not measured
    signal = coverage_from_diff_cover(report, args.minimum)
    if signal is not None:
        update(folder, "quality", {"coverage_changed_lines": signal})
    return 0


if __name__ == "__main__":
    sys.exit(main())
