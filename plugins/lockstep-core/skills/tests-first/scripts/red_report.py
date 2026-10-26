#!/usr/bin/env python3
"""Run a spec's tests and check that every criterion has a test that is red for the right reason.

  python3 red_report.py --root <repo> --spec 0042 [--pytest "uv run pytest"] [-- <pytest args>]

A test is red for the right reason when it fails on an assertion or NotImplementedError. It is not when it passes,
is skipped, or fails to import, collect or call the code (ImportError, SyntaxError, NameError, AttributeError,
TypeError, a broken fixture). Other exceptions are listed as "check": they may be the behaviour under test.
Prints an AC -> test -> result table and exits 1 if any criterion lacks a correctly red test. With --expect green
(after implementation) every test of every criterion must pass instead. pytest only;
dbt unit tests and eval cases are checked by hand (see SKILL.md).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBLEMS = {"passes", "skipped", "wrong-reason", "collection-error", "not-run"}


def spec_criteria(root: Path, spec_id: str) -> list[str]:
    sys.path.insert(0, str(root / ".lockstep" / "src"))
    try:
        from lockstep_checks.config import load_config
        from lockstep_checks.spec import list_specs
        from lockstep_checks.specdoc import parse_spec
    except ImportError:
        raise SystemExit("red_report: .lockstep/ is missing; set the repo up with the bootstrap-repo skill") from None
    finally:
        sys.path.pop(0)
    specs = list_specs(root, load_config(root))
    if spec_id not in specs:
        raise SystemExit(f"red_report: no spec {spec_id} in the specs folder")
    doc = parse_spec((specs[spec_id] / "spec.md").read_text(encoding="utf-8"))
    return [f"{spec_id}/{ac}" for ac in doc.criteria]


def run_pytest(root: Path, pytest_cmd: str, extra: list[str]) -> dict[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "red.json"
        env = dict(os.environ, LOCKSTEP_RED_REPORT=str(report))
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(HERE), env.get("PYTHONPATH")]))
        cmd = [*shlex.split(pytest_cmd), "-p", "lockstep_red", "-q", "-p", "no:cacheprovider", *extra]
        subprocess.run(cmd, cwd=root, env=env, check=False)
        if not report.exists():
            raise SystemExit(f"red_report: pytest wrote no report; check that `{pytest_cmd}` runs pytest")
        return json.loads(report.read_text(encoding="utf-8"))


def evaluate(
    criteria: list[str], tests: dict[str, dict], expect: str = "red"
) -> tuple[list[tuple[str, str, str, str]], bool]:
    """Rows of (AC, test, result, detail), and whether every criterion is as expected (red or green)."""
    rows, ok = [], True
    for ac in criteria:
        mine = [(node, t) for node, t in tests.items() if ac in t["acs"]]
        if not mine:
            rows.append((ac, "-", "no test", ""))
            ok = False
        for node, t in mine:
            rows.append((ac, node, t["result"], t["detail"]))
        if expect == "green":
            ok = ok and all(t["result"] == "passes" for _, t in mine)
        else:
            ok = ok and any(t["result"] == "red" for _, t in mine)
            ok = ok and not any(t["result"] in PROBLEMS for _, t in mine)
    spec = criteria[0].split("/")[0] + "/" if criteria else ""
    for node, t in tests.items():
        unknown = [a for a in t["acs"] if a.startswith(spec) and a not in criteria]
        if t["result"] == "collection-error":
            rows.append(("-", node, t["result"], t["detail"]))
            ok = False
        elif unknown:
            rows.append((", ".join(unknown), node, "unknown criterion", ""))
            ok = False
    return rows, ok


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = argv[argv.index("--") + 1 :] if "--" in argv else []
    argv = argv[: argv.index("--")] if "--" in argv else argv
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--spec", required=True, help="spec id, e.g. 0042")
    ap.add_argument("--expect", choices=["red", "green"], default="red", help="green: after implementation")
    ap.add_argument("--pytest", default=f"{shlex.quote(sys.executable)} -m pytest", help="command that runs pytest")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    criteria = spec_criteria(root, args.spec)
    rows, ok = evaluate(criteria, run_pytest(root, args.pytest, extra), args.expect)
    print("\n| AC | Test | Result |\n|----|------|--------|")
    for ac, node, result, detail in rows:
        print(f"| {ac} | {node} | {result}{' (' + detail + ')' if detail else ''} |")
    done = "All criteria are red for the right reason." if args.expect == "red" else "All criteria pass."
    print(f"\n{done}" if ok else "\nNot ready: fix the rows above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
