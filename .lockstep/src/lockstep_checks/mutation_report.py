"""Report how many mutants a PR's tests kill, without ever failing the build.

Mutation testing changes the code in small ways (``<`` becomes ``<=``, ``+`` becomes ``-``) and reruns the tests.
A mutant the tests do not notice "survives": the code can be wrong in that way and the tests still pass. The share
of mutants killed says more about a test suite than line coverage does.

This runs mutmut on the Python modules the PR changed under the source folder (``--scope all`` for every module), then
prints the score and annotates each surviving mutant at its line, as a warning. It always exits 0: the score is
information for the author and the reviewer, not a gate. Mutation testing comes from SDTRD, which requires every
mutant killed; Lockstep starts by reporting it.

    python -m lockstep_checks.mutation_report --source-dir src --mutmut "uv run --with mutmut==3.8.0 mutmut"
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import evidence
from .gitdiff import GitError, base_ref, changed_files
from .report import Finding, emit

CHECK = "mutation_report"
CAUGHT = ("killed", "timeout")  # a mutant that hangs the tests is noticed too
MISSED = ("survived", "no tests")

_RESULT = re.compile(r"^\s+(?P<name>\S+): (?P<status>[a-z ]+?)\s*$")
_HUNK = re.compile(r"^@@ -(?P<start>\d+)")


@dataclass(frozen=True)
class Mutant:
    name: str
    status: str
    path: str | None = None
    line: int | None = None
    change: str = ""  # "old line -> new line", for the annotation


def module_name(path: str) -> str:
    """The module mutmut names a file's mutants after: ``src/pkg/mod.py`` -> ``pkg.mod``."""
    parts = path.removesuffix(".py").split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts).removeprefix("src.")


def changed_modules(paths: list[str], source_dir: str) -> list[str]:
    """Modules to mutate: changed Python files under the source folder, tests left out."""
    prefix = source_dir.strip("/") + "/"
    modules = {
        module_name(p)
        for p in paths
        if p.startswith(prefix) and p.endswith(".py") and not Path(p).name.startswith(("test_", "conftest"))
    }
    return sorted(m for m in modules if m)


def patterns_for(modules: list[str]) -> list[str]:
    # Mutant names are <module>.x_<function>__mutmut_<n>, or <module>.xǁ<Class>ǁ<method>__mutmut_<n>.
    # Matching the x prefix keeps pkg out of the patterns for pkg.sub, which `pkg.*` would pull in.
    return [p for m in modules for p in (f"{m}.x_*", f"{m}.xǁ*")]


def parse_results(text: str, patterns: list[str] | None) -> list[Mutant]:
    """Parse ``mutmut results --all true``, keeping the mutants that match the patterns (all if None)."""
    mutants = []
    for line in text.splitlines():
        m = _RESULT.match(line)
        if m and (patterns is None or any(fnmatch.fnmatchcase(m["name"], p) for p in patterns)):
            mutants.append(Mutant(m["name"], m["status"]))
    return mutants


def locate(mutant: Mutant, diff: str, root: Path) -> Mutant:
    """Add the file, line and change from ``mutmut show <name>``, whose diff covers only the mutated function.

    The hunk's line numbers count from the function, so the function's original lines are looked up in the file.
    """
    path = None
    original: list[str] = []  # the function as it is in the file
    offset = None  # index of the first changed line in it
    old = new = ""
    in_hunk = False
    for text in diff.splitlines():
        if text.startswith("--- ") and not in_hunk:
            path = text[4:].strip()
        elif _HUNK.match(text):
            in_hunk = True
        elif not in_hunk or text.startswith("+++ "):
            continue
        elif text.startswith("+"):
            new = new or text[1:].strip()
            offset = len(original) if offset is None else offset
        else:
            if text.startswith("-"):
                old = old or text[1:].strip()
                offset = len(original) if offset is None else offset
            original.append(text[1:])
    if path is None:
        return mutant
    change = f"{old} -> {new}" if old and new else old or new
    return Mutant(mutant.name, mutant.status, path, _find(root / path, original, offset or 0), change)


def _find(file: Path, block: list[str], offset: int) -> int | None:
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    for i in range(len(lines) - len(block) + 1):
        if block and lines[i : i + len(block)] == block:
            return i + 1 + offset
    return None


def summarize(mutants: list[Mutant]) -> str:
    counts = {s: sum(m.status == s for m in mutants) for s in {m.status for m in mutants}}
    caught = sum(counts.get(s, 0) for s in CAUGHT)
    missed = sum(counts.get(s, 0) for s in MISSED)
    if not caught + missed:
        return f"no mutants tested ({len(mutants)} found, none killed or survived)"
    score = round(100 * caught / (caught + missed))
    detail = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()) if s not in CAUGHT)
    return f"mutation score {score}%: {caught} of {caught + missed} mutants caught" + (f" ({detail})" if detail else "")


def findings_for(mutants: list[Mutant], summary: str, max_listed: int) -> list[Finding]:
    missed = [m for m in mutants if m.status in MISSED]
    findings = [Finding("warning", f"{summary}. Report only: this never fails the build.")]
    for m in missed[:max_listed]:
        what = "survived" if m.status == "survived" else "has no test that runs it"
        findings.append(Finding("warning", f"mutant {what}: {m.change or m.name} ({m.name})", m.path, m.line))
    if len(missed) > max_listed:
        findings.append(Finding("warning", f"{len(missed) - max_listed} more missed mutants: run `mutmut browse`"))
    return findings


def _mutmut(cmd: list[str], *args: str, root: Path, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*cmd, *args], cwd=root, check=False, capture_output=capture, text=True, encoding="utf-8")


def report(root: Path, base: str, source_dir: str, mutmut: list[str], everything: bool, max_listed: int) -> int:
    patterns = None
    if not everything:
        try:
            paths = [f.path for f in changed_files(root, base) if f.status != "D"]
        except GitError as e:
            _not_measured("error", f"cannot read the PR's changes: {e}")
            return emit([Finding("warning", f"cannot read the PR's changes, so no mutation report: {e}")], CHECK)
        modules = changed_modules(paths, source_dir)
        if not modules:
            _not_measured("skipped", f"the PR changed no Python modules under {source_dir}/")
            print(f"{CHECK}: no changed Python modules under {source_dir}/, nothing to mutate")
            return 0
        patterns = patterns_for(modules)
        print(f"{CHECK}: mutating {', '.join(modules)}", flush=True)

    findings = []
    try:
        run = _mutmut(mutmut, "run", *(patterns or []), root=root, capture=False)
        results = _mutmut(mutmut, "results", "--all", "true", root=root)
    except OSError as e:
        _not_measured("error", f"cannot run mutmut: {e}")
        return emit([Finding("warning", f"cannot run mutmut ({shlex.join(mutmut)}): {e}")], CHECK)
    if run.returncode != 0:
        findings.append(Finding("warning", f"mutmut run exited {run.returncode}; the score may be incomplete"))
    mutants = parse_results(results.stdout, patterns)
    missed = [m for m in mutants if m.status in MISSED]
    located = {m.name: locate(m, _mutmut(mutmut, "show", m.name, root=root).stdout, root) for m in missed[:max_listed]}
    mutants = [located.get(m.name, m) for m in mutants]
    _record(mutants)
    emit([*findings, *findings_for(mutants, summarize(mutants), max_listed)], CHECK)
    return 0


def _record(mutants: list[Mutant]) -> None:
    """The mutation evidence for the trust summary, when the pipeline asks for it."""
    folder = evidence.evidence_dir()
    if folder is not None:
        counts = {
            "caught": sum(m.status in CAUGHT for m in mutants),
            "survived": sum(m.status == "survived" for m in mutants),
            "no_tests": sum(m.status == "no tests" for m in mutants),
        }
        counts["total"] = counts["caught"] + counts["survived"] + counts["no_tests"]
        evidence.update(folder, "mutation", {"mutation": counts})


def _not_measured(status: str, reason: str) -> None:
    folder = evidence.evidence_dir()
    if folder is not None:
        evidence.not_measured(folder, "mutation", status, reason)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog=f"python -m lockstep_checks.{CHECK}", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--base", help="branch to diff against (default: PR target branch, else origin/main)")
    ap.add_argument("--source-dir", default="src", help="folder whose modules are mutated (default: src)")
    ap.add_argument(
        "--scope", choices=("changed", "all"), default="changed", help="the PR's changed modules (default) or all"
    )
    ap.add_argument("--mutmut", default="mutmut", help="command that runs mutmut (default: mutmut)")
    ap.add_argument("--max-listed", type=int, default=20, help="missed mutants to annotate (default: 20)")
    args = ap.parse_args(argv)
    return report(
        args.root.resolve(),
        base_ref(args.base),
        args.source_dir,
        shlex.split(args.mutmut),
        args.scope == "all",
        args.max_listed,
    )


if __name__ == "__main__":
    sys.exit(main())
