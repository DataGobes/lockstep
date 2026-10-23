#!/usr/bin/env python3
"""Inventory a git repo so review rules can be grounded in what is really there.

Prints JSON: hosting, stacks detected (with evidence paths), folder layout,
naming-prefix stats, existing instruction files, and recently changed files to
sample per area. Stdlib only. Run from anywhere inside the repo:

    python3 scan_repo.py [--root PATH] [--samples N]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import PurePosixPath


def git(root, *args):
    try:
        out = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True)
        return out.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def detect_host(root):
    url = git(root, "remote", "get-url", "origin").strip()
    info = {"remote": url or None, "platform": "unknown"}
    m = re.search(r"dev\.azure\.com[:/](?:v3/)?([^/]+)/([^/]+)/(?:_git/)?([^/]+?)(?:\.git)?$", url)
    m = m or re.search(r"([^/.]+)\.visualstudio\.com/(?:DefaultCollection/)?([^/]+)/_git/([^/]+?)(?:\.git)?$", url)
    if m:
        info.update(platform="azure-devops", organization=m.group(1), project=m.group(2), repository=m.group(3))
        return info
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        info.update(platform="github", owner=m.group(1), repository=m.group(2))
    elif url:
        info["platform"] = "other"
    return info


def default_branch(root):
    ref = git(root, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
    if ref:
        return ref.rsplit("/", 1)[-1]
    for name in ("main", "master", "develop"):
        if git(root, "rev-parse", "--verify", "--quiet", name).strip():
            return name
    return git(root, "branch", "--show-current").strip() or None


def recency(root, limit=400):
    """Map path -> (last commit time, number of commits touching it) over recent history."""
    last, churn = {}, Counter()
    ts = None
    for line in git(root, "log", f"-n{limit}", "--name-only", "--format=@%ct").splitlines():
        if line.startswith("@"):
            ts = int(line[1:])
        elif line.strip():
            churn[line] += 1
            last.setdefault(line, ts)
    return last, churn


def read_head(root, path, n=2048):
    try:
        with open(os.path.join(root, path), "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read(n)
    except OSError:
        return ""


def detect_stacks(root, files):
    fileset = set(files)
    names = defaultdict(list)
    for f in files:
        names[PurePosixPath(f).name].append(f)
    stacks = {}

    def add(key, **kw):
        stacks.setdefault(key, {}).update({k: v for k, v in kw.items() if v})

    for proj in names.get("dbt_project.yml", []):
        base = str(PurePosixPath(proj).parent)
        base = "" if base == "." else base + "/"
        model_files = [f for f in files if f.startswith(base + "models/")]
        layers = Counter(PurePosixPath(f).parts[len(PurePosixPath(base).parts) + 1]
                         for f in model_files if len(PurePosixPath(f).parts) > len(PurePosixPath(base).parts) + 2)
        add("dbt", projects=stacks.get("dbt", {}).get("projects", []) + [proj],
            model_layers=dict(layers.most_common(10)),
            sql_models=sum(f.endswith(".sql") for f in model_files),
            yaml_property_files=sum(f.endswith((".yml", ".yaml")) for f in model_files),
            macros=sum(f.startswith(base + "macros/") and f.endswith(".sql") for f in files),
            singular_tests=sum(f.startswith(base + "tests/") for f in files),
            snapshots=sum(f.startswith(base + "snapshots/") for f in files),
            packages_file=next((p for p in (base + "packages.yml", base + "dependencies.yml") if p in fileset), None))
    for cfg in (".sqlfluff", "setup.cfg", "tox.ini", "pyproject.toml"):
        for p in names.get(cfg, []):
            if "[sqlfluff" in read_head(root, p, 20000):
                add("sqlfluff", config=p)

    py = [f for f in files if f.endswith(".py")]
    if py:
        markers = [p for n in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock", "uv.lock")
                   for p in names.get(n, [])]
        markers += [f for f in files if re.search(r"(^|/)requirements[^/]*\.txt$", f) and f not in markers]
        tools = set()
        for p in names.get("pyproject.toml", []) + names.get("setup.cfg", []) + names.get("tox.ini", []):
            text = read_head(root, p, 50000)
            for tool in ("ruff", "black", "isort", "flake8", "mypy", "pyright", "pytest", "pylint", "poetry", "hatch", "uv"):
                if re.search(rf"\[(tool\.)?{tool}\b", text):
                    tools.add(tool)
        for n, tool in (("ruff.toml", "ruff"), (".ruff.toml", "ruff"), ("mypy.ini", "mypy"), ("pytest.ini", "pytest"),
                        (".flake8", "flake8"), ("conftest.py", "pytest")):
            if names.get(n):
                tools.add(tool)
        packages = sorted({str(PurePosixPath(f).parent) for f in files if f.endswith("__init__.py")
                           and len(PurePosixPath(f).parts) <= 3})[:20]
        tests = [f for f in py if re.search(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)", f)]
        add("python", files=len(py), project_files=markers[:10], tools=sorted(tools), packages=packages,
            test_files=len(tests), src_layout=any(f.startswith("src/") for f in py))

    nb = [f for f in files if f.endswith(".ipynb")]
    dbx = [f for f in py if read_head(root, f, 64).startswith("# Databricks notebook source")]
    if nb or dbx:
        add("notebooks", ipynb=len(nb), databricks_source=len(dbx), examples=(nb + dbx)[:5])

    ci = [f for f in files if re.search(r"(^|/)azure-pipelines[^/]*\.ya?ml$", f) or f.startswith(".azuredevops/")
          and f.endswith((".yml", ".yaml"))]
    ci += [f for f in files if re.search(r"\.ya?ml$", f) and f not in ci and re.search(r"(^|/)(pipelines?|ci|\.pipelines)/", f)
           and re.search(r"^\s*(stages|jobs|steps|trigger)\s*:", read_head(root, f, 4000), re.M)]
    if ci:
        add("azure_pipelines", files=ci[:15])
    gha = [f for f in files if f.startswith(".github/workflows/")]
    if gha:
        add("github_actions", files=gha[:15])
    for key, pattern in (("terraform", r"\.tf$"), ("bicep", r"\.bicep$"), ("docker", r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$"),
                         ("node", r"(^|/)package\.json$"), ("dotnet", r"\.(csproj|sln|fsproj)$"), ("java", r"(^|/)(pom\.xml|build\.gradle(\.kts)?)$"),
                         ("pre_commit", r"(^|/)\.pre-commit-config\.ya?ml$"), ("sql_non_dbt", r"\.sql$")):
        hits = [f for f in files if re.search(pattern, f)]
        if key == "sql_non_dbt" and "dbt" in stacks:
            dbt_bases = [str(PurePosixPath(p).parent) for p in stacks["dbt"]["projects"]]
            hits = [f for f in hits if not any(b == "." or f.startswith(b + "/") for b in dbt_bases)]
        if hits:
            add(key, count=len(hits), examples=hits[:5])
    return stacks


def layout(files):
    by_dir = defaultdict(Counter)
    for f in files:
        parts = PurePosixPath(f).parts
        top = parts[0] if len(parts) > 1 else "(root)"
        by_dir[top][PurePosixPath(f).suffix or PurePosixPath(f).name] += 1
    return {d: {"files": sum(c.values()), "top_extensions": dict(c.most_common(4))}
            for d, c in sorted(by_dir.items(), key=lambda kv: -sum(kv[1].values()))[:25]}


def naming_prefixes(files, min_files=3):
    """Filename prefixes (text before the first '_') per folder, counted recursively.

    Reports a folder when its top 1-3 prefixes cover >=80% of its files, and drops it when
    its nearest reported ancestor already shows the same pattern.
    """
    groups = defaultdict(list)
    for f in files:
        p = PurePosixPath(f)
        if p.suffix in (".sql", ".py", ".ts", ".cs") and not p.name.startswith("_"):
            for anc in list(p.parents)[:-1]:
                groups[(str(anc), p.suffix)].append(p.stem)
    found = {}
    for (folder, ext), stems in groups.items():
        if len(stems) < min_files:
            continue
        prefixes = Counter(s.split("_", 1)[0] + "_" if "_" in s else "(none)" for s in stems)
        top = [(k, n) for k, n in prefixes.most_common(3) if k != "(none)"]
        if top and sum(n for _, n in top) / len(stems) >= 0.8:
            found[(folder, ext)] = {"files": len(stems), "prefixes": dict(top),
                                    "exceptions": [s for s in stems if not any(s.startswith(k) for k, _ in top)][:5]}
    out = {}
    for (folder, ext), info in sorted(found.items()):
        parent = next(((str(a), ext) for a in PurePosixPath(folder).parents if (str(a), ext) in found), None)
        if parent and found[parent]["prefixes"].keys() == info["prefixes"].keys():
            continue
        out[f"{folder}/**/*{ext}"] = info
    return dict(list(out.items())[:30])


def instruction_files(files):
    patterns = {
        "repo_wide": r"^\.(github|azuredevops)/copilot-instructions\.md$",
        "path_scoped": r"^\.(github|azuredevops)/instructions/.+\.instructions\.md$",
        "agent_files": r"(^|/)(AGENTS|CLAUDE|GEMINI)\.md$",
        "conventions_docs": r"(^|/)(CONTRIBUTING|STYLEGUIDE|STYLE_GUIDE|CODING_STANDARDS|CONVENTIONS)\.md$|^docs/(adr|decisions)/",
        "ownership_and_format": r"(^|/)(CODEOWNERS|\.editorconfig)$",
    }
    return {k: [f for f in files if re.search(p, f, re.I)][:20] for k, p in patterns.items()}


def samples(root, files, last, churn, per_area):
    """Most recently changed non-trivial files per (top folder, extension) area, plus hot spots."""
    code_ext = {".sql", ".py", ".yml", ".yaml", ".ipynb", ".ts", ".tsx", ".js", ".cs", ".java", ".tf", ".bicep", ".scala", ".r", ".ps1", ".sh"}
    areas = defaultdict(list)
    for f in files:
        p = PurePosixPath(f)
        try:
            tiny = os.path.getsize(os.path.join(root, f)) < 80
        except OSError:
            tiny = True
        if p.suffix.lower() in code_ext and not tiny:
            areas[f"{p.parts[0] if len(p.parts) > 1 else '(root)'} *{p.suffix}"].append(f)
    picked = {}
    for area, fs in sorted(areas.items(), key=lambda kv: -len(kv[1]))[:15]:
        fs.sort(key=lambda f: -(last.get(f) or 0))
        picked[area] = {"files": len(fs), "sample": fs[:per_area]}
    hot = [f for f, _ in churn.most_common(40) if f in set(files)][:10]
    return picked, hot


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--samples", type=int, default=3, help="files to sample per area")
    args = ap.parse_args()
    root = git(args.root, "rev-parse", "--show-toplevel").strip()
    if not root:
        sys.exit("Not inside a git repository.")
    files = [f for f in git(root, "ls-files").splitlines() if f]
    last, churn = recency(root)
    picked, hot = samples(root, files, last, churn, args.samples)
    ext = Counter(PurePosixPath(f).suffix.lower() or "(none)" for f in files)
    result = {
        "root": root,
        "host": detect_host(root),
        "default_branch": default_branch(root),
        "tracked_files": len(files),
        "extensions": dict(ext.most_common(15)),
        "stacks": detect_stacks(root, files),
        "layout": layout(files),
        "naming_prefixes": naming_prefixes(files),
        "existing_instruction_files": instruction_files(files),
        "sample_files_by_area": picked,
        "hot_spots": hot,
    }
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
