#!/usr/bin/env python3
"""Check that the marketplace, the plugins, the README and the docs agree, or set a plugin's version everywhere.

  python3 tools/check_release.py                                  # check; exit 1 on any problem
  python3 tools/check_release.py --set-version 0.2.0 [--plugin lockstep-core]

Checks: every plugin folder has a plugin.json and a marketplace entry with the same name and version, and every
entry has a folder; every skill's frontmatter name matches its folder; every skill is linked from README.md and has a
page in docs/skills/; and safety_scan.py finds nothing in the files Lockstep ships. --set-version writes the version into plugin.json and the marketplace entry, for one plugin or
for every lockstep-* plugin (then also the marketplace's own version and core/pyproject.toml). Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

MARKETPLACE = ".claude-plugin/marketplace.json"
_NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load(root: Path) -> tuple[dict, dict[str, dict]]:
    market = json.loads((root / MARKETPLACE).read_text(encoding="utf-8"))
    plugins = {}
    for manifest in sorted((root / "plugins").glob("*/.claude-plugin/plugin.json")):
        plugins[manifest.parents[1].name] = json.loads(manifest.read_text(encoding="utf-8"))
    return market, plugins


def check(root: Path) -> list[str]:
    market, plugins = load(root)
    problems = []
    entries = {e["name"]: e for e in market.get("plugins", [])}
    for folder, manifest in plugins.items():
        entry = entries.get(folder)
        if manifest.get("name") != folder:
            problems.append(f"plugins/{folder}: plugin.json name is {manifest.get('name')!r}")
        if entry is None:
            problems.append(f"plugins/{folder}: no entry in {MARKETPLACE}")
        elif entry.get("version") != manifest.get("version"):
            problems.append(
                f"{folder}: version {manifest.get('version')} in plugin.json, {entry.get('version')} in {MARKETPLACE}"
            )
        elif entry.get("source") != f"./plugins/{folder}":
            problems.append(f"{folder}: marketplace source is {entry.get('source')!r}, expected ./plugins/{folder}")
    problems += [f"{MARKETPLACE}: {name} has no folder under plugins/" for name in entries if name not in plugins]

    readme = (root / "README.md").read_text(encoding="utf-8")
    for skill_md in sorted((root / "plugins").glob("*/skills/*/SKILL.md")):
        rel = skill_md.relative_to(root).as_posix()
        folder = skill_md.parent.name
        m = _NAME.search(skill_md.read_text(encoding="utf-8").split("\n---", 1)[0])
        if not m or m[1] != folder:
            problems.append(f"{rel}: frontmatter name should be {folder!r}")
        if f"({rel})" not in readme:
            problems.append(f"{rel}: not linked from README.md")
        if not (root / "docs" / "skills" / f"{folder}.md").is_file():
            problems.append(f"{rel}: no page docs/skills/{folder}.md")
    return problems + _safety_scan().scan(root)


def _safety_scan():
    spec = importlib.util.spec_from_file_location("safety_scan", Path(__file__).resolve().parent / "safety_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_version(root: Path, version: str, plugin: str | None) -> list[str]:
    _, plugins = load(root)
    names = [plugin] if plugin else [n for n in plugins if n.startswith("lockstep-")]
    unknown = [n for n in names if n not in plugins]
    if unknown:
        raise SystemExit(f"check_release: no plugin {', '.join(unknown)}")
    changed = []
    for name in names:
        path = root / "plugins" / name / ".claude-plugin" / "plugin.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(re.sub(r'("version":\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1), encoding="utf-8")
        changed.append(path.relative_to(root).as_posix())
    text = (root / MARKETPLACE).read_text(encoding="utf-8")
    for name in names:
        text = re.sub(
            rf'("name":\s*"{re.escape(name)}",(?:[^{{}}]*?)"version":\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text
        )
    if not plugin:
        text = re.sub(r'("metadata":\s*\{[^}]*?"version":\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1)
        core = root / "core" / "pyproject.toml"
        core.write_text(
            re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', core.read_text(encoding="utf-8"), count=1),
            encoding="utf-8",
        )
        changed.append("core/pyproject.toml")
    (root / MARKETPLACE).write_text(text, encoding="utf-8")
    return [*changed, MARKETPLACE]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--set-version", help="new version, e.g. 0.2.0")
    ap.add_argument("--plugin", help="only this plugin (default with --set-version: every lockstep-* plugin)")
    args = ap.parse_args(argv)
    if args.set_version:
        if not _SEMVER.match(args.set_version):
            ap.error("--set-version takes MAJOR.MINOR.PATCH")
        for path in set_version(args.root, args.set_version, args.plugin):
            print(f"updated {path}")
    problems = check(args.root)
    for p in problems:
        print(p)
    if not problems:
        print("release metadata is consistent")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
