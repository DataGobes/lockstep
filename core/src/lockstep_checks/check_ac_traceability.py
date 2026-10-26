"""Trace every acceptance criterion to a test, and every test reference to a criterion.

Tests name a criterion with the spec id, because every spec numbers from AC-001:
  pytest          @pytest.mark.ac("0042/AC-001")  (in test_*.py / *_test.py)
  dbt unit test   name: ac_0042_001_<what>        (in *.unit_tests.yml)
  dbt data test   meta: {ac: 0042/AC-001}
  eval case       ac field or column: 0042/AC-001

Specs with status tests-locked or implemented must have a test for every active
criterion. ``--spec-only`` lints the specs only (sections, criteria, open questions):
that is the gate for a spec PR.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .cli import run
from .config import Config
from .report import Finding
from .spec import SpecError, list_specs, load_status
from .specdoc import SpecDoc, parse_spec

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "target", "dbt_packages", "logs", "__pycache__", ".pytest_cache"}

_REF = re.compile(r"(?<![\w/])(?P<spec>\d+)/(?P<ac>AC-\d+)\b")
_BARE_REF = re.compile(r"(?<![\w/])AC-\d+\b")
# A decorator or a module-level pytestmark; mentions inside strings or comments do not count.
_PYTEST_MARK = re.compile(r"^[ \t]*(?:@|pytestmark\s*=\s*\[?\s*)(?:pytest\.)?mark\.ac\((?P<args>[^)]*)\)", re.MULTILINE)
_UNIT_TEST_NAME = re.compile(r"^\s*-?\s*name:\s*['\"]?ac_(?P<spec>\d+)_(?P<n>\d+)(?:_|\b)", re.MULTILINE)
_UNIT_TEST_BARE = re.compile(r"^\s*-?\s*name:\s*['\"]?ac_(?P<n>\d+)_[a-z]", re.MULTILINE)
_AC_KEY = re.compile(r"""['"]?\bac['"]?\s*[:=]\s*(?P<rest>.*)""")


@dataclass(frozen=True)
class TestRef:
    spec: str
    ac: str
    path: str
    line: int


def find_test_refs(root: Path, specs_dir: str) -> tuple[list[TestRef], list[Finding]]:
    refs: list[TestRef] = []
    problems: list[Finding] = []
    for path in _walk(root, specs_dir):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if path.suffix == ".py" and (path.name.startswith("test_") or path.stem.endswith("_test")):
            _scan_py(text, rel, refs, problems)
        elif rel.endswith((".unit_tests.yml", ".unit_tests.yaml")):
            _scan_unit_tests(text, rel, refs, problems)
            _scan_ac_keys(text, rel, refs, problems)
        elif path.suffix in (".yml", ".yaml", ".sql", ".json", ".jsonl"):
            _scan_ac_keys(text, rel, refs, problems)
        elif path.suffix == ".csv":
            _scan_csv(text, rel, refs, problems)
    return refs, problems


def _walk(root: Path, specs_dir: str):
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and f"{rel_dir}/{d}".lstrip("./") != specs_dir)
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _bare(rel: str, line: int, what: str) -> Finding:
    return Finding("error", f"{what} has no spec id; write it as <spec id>/AC-<n>, e.g. 0042/AC-001", rel, line)


def _scan_py(text: str, rel: str, refs: list[TestRef], problems: list[Finding]) -> None:
    for m in _PYTEST_MARK.finditer(text):
        line = _line_of(text, m.start())
        args = m["args"]
        found = list(_REF.finditer(args))
        refs.extend(TestRef(r["spec"], r["ac"], rel, line) for r in found)
        if not found or _BARE_REF.search(_REF.sub("", args)):
            problems.append(_bare(rel, line, "pytest.mark.ac"))


def _scan_unit_tests(text: str, rel: str, refs: list[TestRef], problems: list[Finding]) -> None:
    for m in _UNIT_TEST_NAME.finditer(text):
        refs.append(TestRef(m["spec"], f"AC-{m['n']}", rel, _line_of(text, m.start())))
    for m in _UNIT_TEST_BARE.finditer(text):  # ac_001_<what>: the old, unqualified form
        problems.append(_bare(rel, _line_of(text, m.start()), "unit test name"))


def _scan_ac_keys(text: str, rel: str, refs: list[TestRef], problems: list[Finding]) -> None:
    for n, line in enumerate(text.splitlines(), start=1):
        for m in _AC_KEY.finditer(line):
            rest = m["rest"]
            found = list(_REF.finditer(rest))
            refs.extend(TestRef(r["spec"], r["ac"], rel, n) for r in found)
            if _BARE_REF.search(_REF.sub("", rest)):
                problems.append(_bare(rel, n, "ac reference"))


def _scan_csv(text: str, rel: str, refs: list[TestRef], problems: list[Finding]) -> None:
    rows = csv.reader(io.StringIO(text))
    header = next(rows, None)
    if not header or "ac" not in [h.strip().lower() for h in header]:
        return
    col = [h.strip().lower() for h in header].index("ac")
    for n, row in enumerate(rows, start=2):
        cell = row[col] if col < len(row) else ""
        found = list(_REF.finditer(cell))
        refs.extend(TestRef(r["spec"], r["ac"], rel, n) for r in found)
        if _BARE_REF.search(_REF.sub("", cell)):
            problems.append(_bare(rel, n, "ac column"))


def check_traceability(root: Path, cfg: Config, spec_only: bool) -> list[Finding]:
    findings: list[Finding] = []
    docs: dict[str, tuple[Path, SpecDoc, bool]] = {}  # spec id -> (folder, parsed spec.md, tests locked?)
    for spec_id, spec_dir in list_specs(root, cfg).items():
        md = spec_dir / "spec.md"
        rel_md = md.relative_to(root).as_posix()
        try:
            status = load_status(root, spec_dir, cfg)
        except SpecError as e:
            findings.append(Finding("error", str(e)))
            continue
        try:
            doc = parse_spec(md.read_text(encoding="utf-8"), cfg.specs.ac_format)
        except FileNotFoundError:
            findings.append(Finding("error", "spec.md is missing", rel_md))
            continue
        findings.extend(Finding("error", msg, rel_md, line) for line, msg in doc.problems)
        if status.status != "draft":
            for line, q in doc.open_questions():
                msg = f"open question must be resolved before '{status.status}': {q}"
                findings.append(Finding("error", msg, rel_md, line))
        docs[spec_id] = (spec_dir, doc, status.tests_locked)
    findings.extend(_check_cross_spec_pointers(root, docs))
    if spec_only:
        return findings

    refs, problems = find_test_refs(root, cfg.specs_dir)
    findings.extend(problems)
    covered: set[tuple[str, str]] = set()
    for r in refs:
        if r.spec not in docs:
            findings.append(Finding("error", f"{r.spec}/{r.ac}: no spec {r.spec} in {cfg.specs_dir}/", r.path, r.line))
            continue
        spec_dir, doc, _ = docs[r.spec]
        if r.ac in doc.criteria:
            covered.add((r.spec, r.ac))
        elif r.ac in doc.superseded:
            spec, ac = doc.replacements.get(r.ac, (None, "its replacement"))
            target = f"{spec or r.spec}/{ac}" if ac.startswith("AC-") else ac
            msg = f"{r.spec}/{r.ac} is superseded; point the test at {target} in a [test-change] PR"
            findings.append(Finding("warning", msg, r.path, r.line))
        else:
            findings.append(Finding("error", f"{r.spec}/{r.ac}: spec {spec_dir.name} has no {r.ac}", r.path, r.line))

    for spec_id, (spec_dir, doc, locked) in docs.items():
        if not locked:
            continue  # tests are written in the test PR that sets tests-locked
        rel_md = (spec_dir / "spec.md").relative_to(root).as_posix()
        for ac, line in doc.criteria.items():
            if (spec_id, ac) not in covered:
                findings.append(Finding("error", f"{spec_id}/{ac} has no test", rel_md, line))
    return findings


def _check_cross_spec_pointers(root: Path, docs: dict[str, tuple[Path, SpecDoc, bool]]) -> list[Finding]:
    findings = []
    for spec_id, (spec_dir, doc, _) in docs.items():
        rel_md = (spec_dir / "spec.md").relative_to(root).as_posix()
        for ac, (spec, target) in doc.replacements.items():
            if spec is None or (spec == spec_id and target in doc.criteria):
                continue
            if spec not in docs:
                msg = f"{ac} is superseded by {spec}/{target}, but there is no spec {spec}"
            elif target not in docs[spec][1].criteria:
                msg = f"{ac} is superseded by {spec}/{target}, which is not an active criterion of spec {spec}"
            else:
                continue
            findings.append(Finding("error", msg, rel_md, doc.superseded[ac]))
    return findings


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    spec_only = "--spec-only" in argv
    if spec_only:
        argv.remove("--spec-only")
    return run(
        "check_ac_traceability",
        __doc__.splitlines()[0] + " Add --spec-only to lint specs only.",
        lambda ctx: check_traceability(ctx.root, ctx.cfg, spec_only),
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
