#!/usr/bin/env python3
"""Check eval cases before they go into a golden dataset.

  python3 check_cases.py --root <repo> evals/datasets/<name>.jsonl [more files]

Each case is one JSON object per line (or a CSV row) shaped like an MLflow GenAI evaluation record, plus Lockstep's
fields: `id` (unique), `ac` (the criterion, `<spec>/AC-<n>`, that must exist in specs/), `inputs` and `expectations`
(non-empty). A case fails when it looks like real personal data: an email address, a phone number or an IBAN.
Prints one line per problem and exits 1 if there is any. Stdlib only; reads the specs with the core in .lockstep/src.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d ()./-]{7,}\d(?!\w)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
_AC = re.compile(r"^(\d+)/(AC-\d+)$")
# Invented-domain addresses are fine in synthetic data.
_SAFE_EMAIL = re.compile(r"@(?:[\w-]+\.)*example\.(?:com|org|net|invalid)\b|\.invalid\b")


def criteria(root: Path) -> set[str]:
    sys.path.insert(0, str(root / ".lockstep" / "src"))
    try:
        from lockstep_checks.config import load_config
        from lockstep_checks.spec import list_specs
        from lockstep_checks.specdoc import parse_spec
    except ImportError:
        raise SystemExit("check_cases: .lockstep/ is missing; set the repo up with the bootstrap-repo skill") from None
    finally:
        sys.path.pop(0)
    found = set()
    for spec_id, folder in list_specs(root, load_config(root)).items():
        md = folder / "spec.md"
        if md.is_file():
            found |= {f"{spec_id}/{ac}" for ac in parse_spec(md.read_text(encoding="utf-8")).criteria}
    return found


def read_cases(path: Path) -> list[tuple[int, dict | None]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".csv":
        rows = []
        for n, row in enumerate(csv.DictReader(text.splitlines()), start=2):
            for key in ("inputs", "expectations"):
                try:
                    row[key] = json.loads(row.get(key) or "null")
                except json.JSONDecodeError:
                    pass
            rows.append((n, row))
        return rows
    rows = []
    for n, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            try:
                rows.append((n, json.loads(line)))
            except json.JSONDecodeError:
                rows.append((n, None))
    return rows


_DATETIME = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b|\b\d{1,2}:\d{2}\b")


def _is_phone(candidate: str) -> bool:
    return sum(c.isdigit() for c in candidate) >= 9


def personal_data(value) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    found = []
    if any(not _SAFE_EMAIL.search(m.group()) for m in _EMAIL.finditer(text)):
        found.append("an email address")
    # Dates and times are not phone numbers.
    if any(_is_phone(m.group()) for m in _PHONE.finditer(_DATETIME.sub(" ", _EMAIL.sub("", text)))):
        found.append("a phone number")
    if _IBAN.search(text):
        found.append("an IBAN")
    return found


def check(paths: list[Path], known: set[str]) -> list[str]:
    problems, ids = [], {}
    for path in paths:
        for n, case in read_cases(path):
            where = f"{path}:{n}"
            if not isinstance(case, dict):
                problems.append(f"{where}: not a JSON object")
                continue
            cid = case.get("id")
            if not cid:
                problems.append(f"{where}: no id")
            elif cid in ids:
                problems.append(f"{where}: id {cid!r} also used at {ids[cid]}")
            else:
                ids[cid] = where
            ac = str(case.get("ac") or "")
            if not _AC.match(ac):
                problems.append(f"{where}: ac must name a criterion like 0042/AC-001, got {ac!r}")
            elif ac not in known:
                problems.append(f"{where}: {ac} is not a criterion of any spec")
            for key in ("inputs", "expectations"):
                if not case.get(key):
                    problems.append(f"{where}: {key} is empty")
            for what in personal_data({k: v for k, v in case.items() if k not in ("id", "ac")}):
                problems.append(f"{where}: looks like real personal data ({what}); use invented values")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    problems = check([p if p.is_absolute() else root / p for p in args.files], criteria(root))
    for p in problems:
        print(p)
    print(f"{len(problems)} problem(s)" if problems else "check_cases: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
