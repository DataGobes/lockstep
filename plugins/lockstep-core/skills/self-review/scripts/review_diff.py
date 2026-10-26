#!/usr/bin/env python3
"""Collect the facts a self-review needs from the branch's diff against main.

  python3 review_diff.py --root <repo> [--base origin/main] [--python "uv run python"] [--spec 0042]

Reports, as Markdown: every changed file (to compare with the spec's scope), existing protected files that changed
(tests, fixtures, thresholds), added lines that may mask errors (broad except, suppress, coalesce, try_cast, ...),
and new Python imports that do not resolve in the repo's environment, including names missing from a module, the
usual sign of an invented API. With --spec it also lists the spec's criteria with their text, for the spec pass to
quote. It judges nothing else; the skill does. Uses the Lockstep core in .lockstep/src.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

MASKING = (
    ((".py",), re.compile(r"^\s*except\s*:"), "bare except"),
    ((".py",), re.compile(r"^\s*except\s*\(?\s*(?:Exception|BaseException)\b"), "broad except"),
    ((".py",), re.compile(r"\bcontextlib\.suppress\(|^\s*with\s+suppress\("), "suppressed exception"),
    ((".py",), re.compile(r"^\s*except\b.*:\s*(?:pass|\.\.\.|continue)\s*$"), "exception swallowed"),
    ((".sql",), re.compile(r"\b(?:coalesce|ifnull|nvl|zeroifnull)\s*\(", re.IGNORECASE), "null replaced"),
    ((".sql",), re.compile(r"\b(?:try_cast|try_to_\w+|try_divide)\s*\(", re.IGNORECASE), "failed cast hidden"),
)
_IMPORT = re.compile(
    r"^\s*(?:from\s+(?P<mod>[\w.]+)\s+import\s+(?P<names>[\w, ()]+)|import\s+(?P<mods>[\w., ]+))\s*(?:#.*)?$"
)

_PROBE = """
import importlib, json, sys
out = []
for mod, names in json.loads(sys.argv[1]):
    try:
        m = importlib.import_module(mod)
    except Exception as e:
        out.append([mod, None, type(e).__name__])
        continue
    for n in names:
        if not hasattr(m, n):
            try:
                importlib.import_module(mod + "." + n)
            except Exception:
                out.append([mod, n, "missing"])
print(json.dumps(out))
"""


def load_core(root: Path):
    sys.path.insert(0, str(root / ".lockstep" / "src"))
    try:
        from lockstep_checks import config, gitdiff, paths, spec, specdoc
    except ImportError:
        raise SystemExit("review_diff: .lockstep/ is missing; set the repo up with the bootstrap-repo skill") from None
    finally:
        sys.path.pop(0)
    return config, gitdiff, paths, spec, specdoc


def criteria_text(root: Path, cfg, spec, specdoc, spec_id: str) -> list[str]:
    folder = spec.list_specs(root, cfg).get(spec_id)
    if folder is None:
        return [f"- no spec {spec_id} in {cfg.specs_dir}/"]
    lines = (folder / "spec.md").read_text(encoding="utf-8").splitlines()
    doc = specdoc.parse_spec("\n".join(lines))
    return [f"- {lines[n - 1].strip().lstrip('-*0123456789. ')}" for n in doc.criteria.values()] or ["- none"]


def new_imports(files) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for f in files:
        if not f.path.endswith(".py"):
            continue
        for _, line in f.added_lines:
            m = _IMPORT.match(line)
            if not m:
                continue
            if m["mod"]:
                if m["mod"].startswith("."):
                    continue
                names = {n.strip(" ()").split(" as ")[0] for n in m["names"].split(",") if n.strip(" ()")}
                found.setdefault(m["mod"], set()).update(names)
            else:
                for mod in m["mods"].split(","):
                    found.setdefault(mod.strip().split(" as ")[0], set())
    return found


def probe(root: Path, python: str, imports: dict[str, set[str]]) -> list[tuple[str, str | None, str]] | str:
    if not imports:
        return []
    payload = json.dumps([[m, sorted(n)] for m, n in sorted(imports.items())])
    p = subprocess.run(
        [*shlex.split(python), "-c", _PROBE, payload], cwd=root, check=False, capture_output=True, text=True
    )
    if p.returncode != 0:
        return f"could not run `{python}`: {p.stderr.strip()[-300:]}"
    return [tuple(row) for row in json.loads(p.stdout)]


def review(root: Path, base: str | None, python: str, spec_id: str | None = None) -> str:
    config, gitdiff, paths, spec, specdoc = load_core(root)
    cfg = config.load_config(root)
    files = gitdiff.changed_files(root, gitdiff.base_ref(base))
    out = [f"## Changed files ({len(files)})", ""]
    out += [f"- `{f.status}` {f.path}" for f in sorted(files, key=lambda f: f.path)] or ["- none"]

    protected = [f for f in files if f.existed_on_base and paths.matches_any(f.base_path, cfg.protect.globs)]
    out += ["", "## Existing protected files changed", ""]
    out += [f"- {f.path} ({f.status})" for f in protected] or ["- none"]

    masking = [
        f"- {f.path}:{n}: {label}: `{line.strip()[:100]}`"
        for f in files
        for n, line in f.added_lines
        for suffixes, rx, label in MASKING
        if f.path.endswith(suffixes) and rx.search(line)
    ]
    out += ["", "## Added lines that may mask errors", ""] + (masking or ["- none"])

    result = probe(root, python, new_imports(files))
    out += ["", "## Imports that do not resolve", ""]
    if isinstance(result, str):
        out.append(f"- not checked: {result}")
    else:
        out += [f"- `{mod}`: {why}" if name is None else f"- `{mod}.{name}`: not found" for mod, name, why in result]
        out += [] if result else ["- none"]
    if spec_id:
        out += ["", f"## Criteria of spec {spec_id}", ""] + criteria_text(root, cfg, spec, specdoc, spec_id)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--base", help="branch to diff against (default: origin/main)")
    ap.add_argument("--python", default=shlex.quote(sys.executable), help="the repo's Python, e.g. 'uv run python'")
    ap.add_argument("--spec", help="spec id, e.g. 0042: also list its criteria")
    args = ap.parse_args(argv)
    print(review(args.root.resolve(), args.base, args.python, args.spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
