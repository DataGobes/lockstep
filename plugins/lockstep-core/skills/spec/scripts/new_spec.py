#!/usr/bin/env python3
"""Create a new spec folder from the repo's spec template, with the next free id.

  python3 new_spec.py --root <repo> --title "Churn features" --track data --pii no [--jira MXAAI-123]

Copies specs/_template/ to specs/<id>-<slug>/, fills in the id, title and status.yml, and prints JSON with the folder,
the id and the branches. By default the spec goes in one PR with its failing tests: "branch" is test/<id>-<slug>, made
from "feature_branch" (feature/<id>-<slug>). A spec that needs a spec PR first (python -m lockstep_checks.spec_pr <id>
says) uses "spec_pr_branch" (spec/<id>-<slug>) instead. With --baseline, "branch" is baseline/<id>-<slug>. The id is one more
than the highest id in the working tree, on origin/main and in the spec/, test/, feature/ and baseline/ branch names
(local and fetched), so a spec someone merged since you branched, or one still on its branches, is not reused. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

_ID = re.compile(r"^(\d+)-")
_BRANCH_ID = re.compile(r"(?:^|/)(?:spec|test|feature|baseline)/(\d+)-")
_JIRA = re.compile(r"[A-Z][A-Z0-9_]+-[1-9]\d*")


class SpecError(RuntimeError):
    pass


def slugify(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title.replace("ß", "ss")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return "-".join(slug.split("-")[:6]) or "spec"


def used_ids(root: Path, specs_dir: str) -> set[int]:
    names = {p.name for p in (root / specs_dir).iterdir()} if (root / specs_dir).is_dir() else set()
    p = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "--name-only", f"origin/main:{specs_dir}"],
        check=False,
        capture_output=True,
        text=True,
    )
    names |= set(p.stdout.split()) if p.returncode == 0 else set()
    ids = {int(m[1]) for name in names if (m := _ID.match(name))}
    # Specs still on their branches: someone's spec PR, or a spec in its test PR that reaches main only with its code.
    refs = subprocess.run(
        ["git", "-C", str(root), "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"],
        check=False,
        capture_output=True,
        text=True,
    ).stdout
    return ids | {int(m[1]) for ref in refs.split() if (m := _BRANCH_ID.search(ref))}


def fill_status(
    text: str,
    track: str,
    pii: str,
    jira: str | None,
    design: str | None = None,
    capability: str | None = None,
    kind: str | None = None,
    contract: str | None = None,
) -> str:
    lines = text.splitlines()
    filled = (
        ("pii", pii),
        ("track", track),
        ("jira", jira),
        ("design", design),
        ("capability", capability),
        ("contract", contract),
    )
    for key, value in (*filled, ("kind", kind)):
        for i, line in enumerate(lines):
            if value is not None and re.match(rf"{key}:(\s|$)", line):
                hash_at = line.find("#")
                new = f"{key}: {value}"
                # Keep the template's comment, in its column.
                lines[i] = new.ljust(max(hash_at, len(new) + 1)) + line[hash_at:] if hash_at >= 0 else new
                break
    return "\n".join(lines) + "\n"


def fill_spec(text: str, spec_id: str, title: str) -> str:
    text = re.sub(r"^id: .*$", f"id: {spec_id}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^title: .*$", f"title: {title}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^# .*$", f"# {title}", text, count=1, flags=re.MULTILINE)
    # Examples in the template use 0042; point them at this spec.
    return text.replace("0042/", f"{spec_id}/").replace("ac_0042_", f"ac_{spec_id}_")


def create(
    root: Path,
    title: str,
    track: str,
    pii: str,
    jira: str | None,
    specs_dir: str = "specs",
    spec_id: str | None = None,
    slug: str | None = None,
    design: bool = False,
    capability: str | None = None,
    baseline: bool = False,
    contract: bool = False,
) -> dict:
    template = root / specs_dir / "_template"
    if not (template / "spec.md").is_file() or not (template / "status.yml").is_file():
        raise SpecError(f"{template.relative_to(root)} is missing; set the repo up with the bootstrap-repo skill first")
    if contract and "\ncontract:" not in "\n" + (template / "status.yml").read_text(encoding="utf-8"):
        raise SpecError(
            f"{(template / 'status.yml').relative_to(root)} has no contract: line; run bootstrap-repo to update it"
        )
    if baseline and not (template / "baseline" / "spec.md").is_file():
        raise SpecError(
            f"{(template / 'baseline').relative_to(root)}/spec.md is missing; run bootstrap-repo to update it"
        )
    taken = used_ids(root, specs_dir)
    if spec_id is None:
        spec_id = f"{max(taken, default=0) + 1:04d}"
    elif int(spec_id) in taken:
        raise SpecError(f"spec id {spec_id} is already used")
    slug = slug or slugify(title)
    folder = root / specs_dir / f"{spec_id}-{slug}"
    # design/ holds research.md and design.md, for specs that take the research and design step; baseline/ the spec.md
    # for a baseline spec, which describes behaviour the code already has.
    shutil.copytree(template, folder, ignore=shutil.ignore_patterns("design", "baseline"))
    if baseline:
        shutil.copyfile(template / "baseline" / "spec.md", folder / "spec.md")
    if design and (template / "design").is_dir():
        for doc in sorted((template / "design").glob("*.md")):
            (folder / doc.name).write_text(
                doc.read_text(encoding="utf-8").replace("<short title>", title), encoding="utf-8"
            )
    spec_md, status = folder / "spec.md", folder / "status.yml"
    spec_md.write_text(fill_spec(spec_md.read_text(encoding="utf-8"), spec_id, title), encoding="utf-8")
    status.write_text(
        fill_status(
            status.read_text(encoding="utf-8"),
            track,
            pii,
            jira,
            "yes" if design else None,
            capability,
            "baseline" if baseline else None,
            "yes" if contract else None,
        ),
        encoding="utf-8",
    )
    name = f"{spec_id}-{slug}"
    found = {"id": spec_id, "spec_dir": folder.relative_to(root).as_posix()}
    if baseline:
        return {**found, "branch": f"baseline/{name}"}
    return {**found, "branch": f"test/{name}", "feature_branch": f"feature/{name}", "spec_pr_branch": f"spec/{name}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--title", required=True)
    ap.add_argument("--track", required=True, choices=["data", "ai", "mixed"])
    ap.add_argument("--pii", required=True, choices=["yes", "no"])
    ap.add_argument("--jira", help="Jira issue key, e.g. MXAAI-123")
    ap.add_argument("--id", dest="spec_id", help="use this id instead of the next free one")
    ap.add_argument("--slug", help="folder slug (default: from the title)")
    ap.add_argument("--specs-dir", default="specs")
    ap.add_argument("--design", action="store_true", help="add research.md and design.md (large specs)")
    ap.add_argument("--capability", help="living spec the criteria belong to, e.g. churn-scoring")
    ap.add_argument("--baseline", action="store_true", help="pin behaviour the code already has (kind: baseline)")
    ap.add_argument(
        "--contract", action="store_true", help="changes an enforced data contract or an interface others use"
    )
    args = ap.parse_args(argv)
    if args.jira and not _JIRA.fullmatch(args.jira):
        ap.error("--jira takes an issue key such as MXAAI-123")
    if args.spec_id and not re.fullmatch(r"\d{4}", args.spec_id):
        ap.error("--id takes four digits, e.g. 0042")
    if args.capability and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.capability):
        ap.error("--capability takes lower-case words joined by hyphens")
    if args.slug and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        ap.error("--slug takes lower-case words joined by hyphens")
    try:
        result = create(
            args.root.resolve(),
            args.title,
            args.track,
            args.pii,
            args.jira,
            args.specs_dir,
            args.spec_id,
            args.slug,
            args.design,
            args.capability,
            args.baseline,
            args.contract,
        )
    except SpecError as e:
        print(f"new_spec: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
