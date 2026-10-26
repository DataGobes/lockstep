"""Say whether a spec goes through a spec PR of its own, or straight into its test PR.

  python -m lockstep_checks.spec_pr <id> [--root <repo>] [--json]

One PR is the default: the spec arrives in the test PR with its failing tests, and the reviewer approves both
together. A spec gets its own spec PR first when it crosses a line in ``[specs]``: more active criteria than
``spec_pr_above_criteria``, or a trait in ``spec_pr_for`` (the research and design step, an interface change marked
``contract: yes``, personal data). The ``spec`` skill asks this before it picks the branch; ``check_spec_required``
asks it of a test PR that adds its spec.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config, ConfigError, load_config
from .spec import SpecError, list_specs, load_status
from .specdoc import parse_spec
from .status import SpecStatus


def reasons(spec_md: str, status: SpecStatus | None, cfg: Config) -> list[str]:
    """Why this spec needs a spec PR of its own before its test PR; empty when it may go in one PR."""
    s = cfg.specs
    found = []
    count = len(parse_spec(spec_md, s.ac_format).criteria)
    if count > s.spec_pr_above_criteria:
        found.append(
            "every spec gets a spec PR first in this repo ([specs] spec_pr_above_criteria = 0)"
            if s.spec_pr_above_criteria == 0
            else f"it has {count} criteria, more than [specs] spec_pr_above_criteria = {s.spec_pr_above_criteria}"
        )
    if status is not None:
        traits = {
            "design": (status.design, "it takes the research and design step"),
            "contract": (status.contract, "it changes a contract or interface others use (contract: yes)"),
            "pii": (status.pii, "it touches personal data (pii: yes)"),
        }
        found += [why for name, (has, why) in traits.items() if has and name in s.spec_pr_for]
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m lockstep_checks.spec_pr", description=__doc__.splitlines()[0])
    ap.add_argument("spec_id", help="the spec's id, e.g. 0042")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        cfg = load_config(root)
        folder = list_specs(root, cfg).get(args.spec_id)
        if folder is None:
            raise SpecError(f"no spec {args.spec_id} under {cfg.specs_dir}/")
        status = load_status(root, folder, cfg)
        text = (folder / "spec.md").read_text(encoding="utf-8")
    except (ConfigError, SpecError, OSError) as e:
        print(f"lockstep_checks: {e}", file=sys.stderr)
        return 1
    why = reasons(text, status, cfg)
    if args.json:
        print(json.dumps({"spec": args.spec_id, "spec_pr": bool(why), "reasons": why}, indent=2))
    elif why:
        print(f"Spec {args.spec_id} gets a spec PR of its own first: " + "; ".join(why) + ".")
    else:
        print(f"Spec {args.spec_id} goes in one PR with its failing tests.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
