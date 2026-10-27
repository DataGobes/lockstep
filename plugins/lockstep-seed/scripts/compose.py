#!/usr/bin/env python3
"""Compose a team's workflow from the fixed core and the practice catalogue, render it, and log every change.

  python3 compose.py plan   --root <repo> [--answers answers.toml] [--catalog <dir>]...   # proposal, writes nothing
  python3 compose.py apply  --root <repo> [--answers answers.toml] [--catalog <dir>]...   # first seeding
  python3 compose.py add    --root <repo> --practice <id> --reason "<failure seen>" [--evidence "<link or note>"]
  python3 compose.py remove --root <repo> --practice <id> --reason "<why it no longer earns its place>"
  python3 compose.py render --root <repo>                                              # re-render, log nothing

`.workflow/workflow.toml` is the desired state; every other file is rendered from it. `.workflow/ledger.jsonl` is
the history: one event per change, with its reason. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN / "core"))
import probe as probe_mod
from seedcore import CONFIG, DEFAULT_CORE, LEDGER, LOCKS, WORKFLOW

MANIFEST = WORKFLOW / "rendered.json"
REPO_CATALOG = WORKFLOW / "practices"
BEGIN = "<!-- seed:begin: generated from .workflow/workflow.toml; change it with /grow-workflow, not by hand -->"
END = "<!-- seed:end -->"
MAX_LINES = 40
MAX_PRACTICES = 5
MAX_AUTHORED = 2  # practices the agent wrote itself, at seeding
MAX_AUTHORED_LINES = 2
STARTS = {"risk", "context", "evidence"}
CORE_LINES = [
    "Tests listed in `.workflow/locks.toml` are locked: never edit one to make code pass. If it looks wrong, stop and say so.",
    "Every acceptance criterion gets a test that names it (`{ac_example}`).",
    "Workflow changes go through `/grow-workflow`, which logs the reason in `.workflow/ledger.jsonl`.",
]
HOOK_COMMAND = 'python3 "${CLAUDE_PROJECT_DIR:-.}/.workflow/core/protect_locked.py"'
HOOK_MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell"
CORE_FILES = ["seedcore.py", "protect_locked.py", "check_core.py"]
CI_FILES = {
    "ci_github": ("ci/github-seed-core.yml", ".github/workflows/seed-core.yml"),
    "ci_ado": ("ci/azure-pipelines-seed-core.yml", "azure-pipelines-seed-core.yml"),
}


class ComposeError(Exception):
    pass


# ---------- catalogue ----------


def load_catalog(layers: list[Path]) -> dict[str, dict]:
    """Every practice, later layers replacing earlier ones with the same id."""
    catalog: dict[str, dict] = {}
    for layer in layers:
        if not layer.is_dir():
            continue
        for f in sorted(layer.glob("*.toml")):
            try:
                p = tomllib.loads(f.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                raise ComposeError(f"{f}: not valid TOML: {e}") from e
            for key in ("id", "title", "prevents", "start"):
                if not p.get(key):
                    raise ComposeError(f"{f}: missing `{key}`")
            if p["start"] not in STARTS:
                raise ComposeError(f"{f}: start must be one of {sorted(STARTS)}")
            if p.get("authored_by") == "agent":
                check_authored(f, p, catalog)
            p["_layer"] = str(layer)
            p["_file"] = str(f)
            catalog[p["id"]] = p
    return catalog


def check_authored(f: Path, p: dict, catalog: dict[str, dict]) -> None:
    """A practice the agent wrote is held to SEED.md section 2b: new id, a named failure, one or two short lines."""
    if p["id"] in catalog:
        raise ComposeError(
            f"{f}: agent-written practice reuses the id {p['id']!r}; give it a new id, and decline the shipped one "
            "if it should not apply"
        )
    if not p.get("failures"):
        raise ComposeError(f"{f}: agent-written practice needs `failures`: what goes wrong without it")
    lines = p.get("render", {}).get("agents_md", [])
    if len(lines) > MAX_AUTHORED_LINES:
        raise ComposeError(
            f"{f}: agent-written practice has {len(lines)} AGENTS.md lines; at most {MAX_AUTHORED_LINES}"
        )
    if not lines and not any(p.get("render", {}).get(k) for k in ("deny", "ask", "create")):
        raise ComposeError(f"{f}: agent-written practice renders nothing")


def authored(p: dict) -> bool:
    return p.get("authored_by") == "agent"


def layers(root: Path, extra: list[Path]) -> list[Path]:
    return [PLUGIN / "catalog", *extra, root / REPO_CATALOG]


# ---------- planning ----------


def plan(profile: dict, answers: dict, catalog: dict[str, dict]) -> dict:
    """Which practices to start with, and why; the rest become candidates. Implements SEED.md section 2."""
    signals = set(profile["signals"])
    evidence = {e["practice"]: e for e in answers.get("evidence", []) if isinstance(e, dict) and e.get("practice")}
    declined = {d["practice"]: d.get("reason", "") for d in answers.get("decline", []) if isinstance(d, dict)}
    unknown = sorted((set(evidence) | set(declined)) - set(catalog))
    if unknown:
        raise ComposeError(f"answers name practices not in the catalogue: {', '.join(unknown)}")
    selected, candidates = [], []
    for pid, p in sorted(catalog.items()):
        hits = sorted(signals & set(p.get("signals", [])))
        relevant = not p.get("signals") or bool(hits)
        said = [a for a in p.get("answers", []) if answers.get(a) is True]
        reason, source = None, None
        if pid in evidence:
            reason, source = evidence[pid].get("failure", "").strip(), "evidence"
            if not reason:
                raise ComposeError(f"evidence for {pid} names no failure")
        elif said:
            reason, source = "the team answered " + ", ".join(f"{a} = yes" for a in said), "answer"
        elif p["start"] == "risk" and hits:
            reason, source = "the repo can reach this harm: " + ", ".join(hits), "risk"
        elif p["start"] == "context" and relevant:
            reason, source = "the agent cannot find this out itself", "context"
        if reason and pid in declined:
            candidates.append({"id": pid, "why": f"declined by the team: {declined[pid] or 'no reason given'}"})
        elif reason:
            selected.append({"id": pid, "reason": reason, "source": source, "authored": authored(p)})
        elif relevant:
            candidates.append({"id": pid, "why": "add when the team sees: " + "; ".join(p.get("failures", [])[:2])})
    return {"selected": selected, "candidates": candidates, "declined": declined}


# ---------- rendering ----------


def fill(line: str, commands: dict) -> str | None:
    """Fill {test}, {lint}, {build}; None when a command it needs is unknown."""
    needed = re.findall(r"\{(\w+)\}", line)
    if any(n not in commands for n in needed):
        return None
    return line.format(**commands)


def agents_lines(workflow: dict, catalog: dict) -> list[str]:
    cfg = workflow["core"]
    ac_example = "AC-001" if cfg["ac_scope"] == "global" else "0001/AC-001"
    lines = ["## Working rules", ""]
    for p in workflow["practice"]:
        for raw in catalog[p["id"]].get("render", {}).get("agents_md", []):
            line = fill(raw, workflow.get("commands", {}))
            if line:
                lines.append(f"- {line}")
    lines += ["", "## Fixed core", ""] + [f"- {x.format(ac_example=ac_example)}" for x in CORE_LINES]
    recommend = [r for p in workflow["practice"] for r in catalog[p["id"]].get("render", {}).get("recommend", [])]
    if recommend:
        lines += ["", "Skills for this repo: " + ", ".join(dict.fromkeys(recommend)) + "."]
    return lines


def budget_errors(workflow: dict, catalog: dict) -> list[str]:
    errors = []
    n = len(agents_lines(workflow, catalog))
    if n > MAX_LINES:
        errors.append(
            f"the generated AGENTS.md block is {n} lines; the budget is {MAX_LINES}. Remove a practice first."
        )
    seeded = [p for p in workflow["practice"] if p.get("source") != "grow"]
    if len(seeded) > MAX_PRACTICES:
        errors.append(f"{len(seeded)} practices at seeding; the budget is {MAX_PRACTICES}. More means guessing.")
    mine = [p["id"] for p in seeded if authored(catalog.get(p["id"], {}))]
    if len(mine) > MAX_AUTHORED:
        errors.append(
            f"{len(mine)} agent-written practices at seeding ({', '.join(mine)}); the budget is {MAX_AUTHORED}. "
            "Prefer a catalogue practice, or wait for evidence."
        )
    return errors


def replace_block(text: str, block: str) -> str:
    start, end = text.find("<!-- seed:begin"), text.find(END)
    if start != -1 and end != -1:
        return text[:start] + block + text[end + len(END) :]
    return text.rstrip() + "\n\n" + block + "\n"


def merge_settings(current: dict, old: dict, new: dict) -> dict:
    """Take out what Seed rendered last time, put in what it renders now; keep everything the repo added."""
    perms = current.setdefault("permissions", {})
    for kind in ("deny", "ask"):
        keep = [r for r in perms.get(kind, []) if r not in old.get(kind, [])]
        perms[kind] = keep + [r for r in new.get(kind, []) if r not in keep]
        if not perms[kind]:
            del perms[kind]
    pre = current.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre[:] = [h for h in pre if not any(x.get("command") == HOOK_COMMAND for x in h.get("hooks", []))]
    pre.append({"matcher": HOOK_MATCHER, "hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    if not perms:
        del current["permissions"]
    return current


def render(root: Path, workflow: dict, catalog: dict, signals: set[str]) -> list[str]:
    """Write every rendered file from the desired state. Returns notes for the person (merge items)."""
    notes = []
    missing = [p["id"] for p in workflow["practice"] if p["id"] not in catalog]
    if missing:
        raise ComposeError(f"workflow.toml names practices not in the catalogue: {', '.join(missing)}")
    errors = budget_errors(workflow, catalog)
    if errors:
        raise ComposeError(" ".join(errors))
    manifest_path = root / MANIFEST
    old = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}

    # AGENTS.md: a managed block; the rest of the file is the team's.
    block = "\n".join([BEGIN, *agents_lines(workflow, catalog), END])
    agents = root / "AGENTS.md"
    if agents.is_file():
        agents.write_text(replace_block(agents.read_text(encoding="utf-8"), block), encoding="utf-8")
    else:
        header = f"# {root.name}\n\n<!-- One or two lines, by a person: what this repo builds and for whom. -->\n\n"
        agents.write_text(header + block + "\n", encoding="utf-8")
    claude = root / "CLAUDE.md"
    if not claude.is_file():
        claude.write_text("@AGENTS.md\n", encoding="utf-8")
    elif "@AGENTS.md" not in claude.read_text(encoding="utf-8"):
        notes.append("merge: CLAUDE.md exists without `@AGENTS.md`; add it as the first line so Claude reads the rules")

    # Permissions and the core hook. Claude Code and Copilot both read .claude/settings.json.
    new = {"deny": [], "ask": []}
    for p in workflow["practice"]:
        r = catalog[p["id"]].get("render", {})
        for kind in ("deny", "ask"):
            new[kind] += [x for x in r.get(kind, []) if x not in new[kind]]
    settings_path = root / ".claude" / "settings.json"
    current = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    settings = merge_settings(current, old.get("settings", {}), new)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    # Starter files a practice needs; created once, then the team's.
    for p in workflow["practice"]:
        for rel, text in catalog[p["id"]].get("render", {}).get("create", {}).items():
            if not (root / rel).exists():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")

    # The fixed core, and its CI check for the pipelines the repo has.
    core = root / WORKFLOW / "core"
    core.mkdir(parents=True, exist_ok=True)
    for f in CORE_FILES:
        shutil.copyfile(PLUGIN / "core" / f, core / f)
    if not (root / LOCKS).is_file():
        (root / LOCKS).write_text(
            "# Test files an agent may not edit. A person adds an entry when a spec's tests are agreed:\n"
            '# [[lock]]\n# path = "tests/test_pricing.py"\n# spec = "specs/0001-pricing.md"\n',
            encoding="utf-8",
        )
    ci_written = []
    for signal, (src, dest) in CI_FILES.items():
        if signal in signals:
            (root / dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PLUGIN / "core" / src, root / dest)
            ci_written.append(dest)
    if not ci_written:
        notes.append(
            "todo: no CI found; run `python3 .workflow/core/check_core.py --base origin/main` in your PR checks"
        )
    manifest = {"settings": new, "files": ci_written, "rendered_at": now()}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return notes


# ---------- state and ledger ----------


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def log(root: Path, action: str, practice: str, reason: str, **extra) -> None:
    event = {"time": now(), "action": action, "practice": practice, "reason": reason, **extra}
    path = root / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def q(value) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string or list is valid TOML for our values


def dump_workflow(w: dict) -> str:
    out = [
        "# The team's workflow: the desired state. compose.py renders every other file from it.",
        "# Change it with /grow-workflow so the ledger records why.",
        "",
        f"version = {w['version']}",
        f"seeded_at = {q(w['seeded_at'])}",
        f"signals = {q(w['signals'])}",
        "",
        "[core]",
    ]
    out += [f"{k} = {q(v)}" for k, v in w["core"].items()]
    out += ["", "[commands]"] + [f"{k} = {q(v)}" for k, v in w.get("commands", {}).items()]
    for p in w["practice"]:
        out += ["", "[[practice]]"] + [f"{k} = {q(v)}" for k, v in p.items()]
    return "\n".join(out) + "\n"


def read_workflow(root: Path) -> dict:
    path = root / CONFIG
    if not path.is_file():
        raise ComposeError(f"{CONFIG} not found; seed the repo first (compose.py apply)")
    w = tomllib.loads(path.read_text(encoding="utf-8"))
    w.setdefault("practice", [])
    w["core"] = DEFAULT_CORE | w.get("core", {})
    return w


def write_workflow(root: Path, w: dict) -> None:
    (root / CONFIG).parent.mkdir(parents=True, exist_ok=True)
    (root / CONFIG).write_text(dump_workflow(w), encoding="utf-8")


def load_answers(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ComposeError(f"cannot read answers {path}: {e}") from e


# ---------- proposal text ----------


def proposal(profile: dict, result: dict, catalog: dict, workflow: dict) -> str:
    out = [
        f"# Proposed workflow for {profile['repo']}",
        "",
        "## Fixed core (every team)",
        "",
        "- core-ac-tests, core-locked-tests, core-ledger (see SEED.md)",
        "",
        "## Start with",
        "",
    ]
    if not result["selected"]:
        out.append("- nothing beyond the core")
    for s in result["selected"]:
        p = catalog[s["id"]]
        out.append(f"- **{s['id']}**: {p['title']}. Why: {s['reason']} ({s['source']}). Cost: {p.get('cost', '?')}.")
        if s.get("authored"):
            rel = Path(p["_file"]).name
            out.append(
                f"  - Agent-written ({REPO_CATALOG.as_posix()}/{rel}): not in the shared catalogue; review its wording."
            )
    out += ["", "## Not yet (add when the failure shows up)", ""]
    out += [f"- {c['id']}: {c['why']}" for c in result["candidates"]] or ["- none"]
    lines = agents_lines(workflow, catalog)
    out += ["", f"## AGENTS.md block ({len(lines)} of {MAX_LINES} lines)", "", "```markdown", *lines, "```"]
    errors = budget_errors(workflow, catalog)
    if errors:
        out += ["", "## Over budget", ""] + [f"- {e}" for e in errors]
    return "\n".join(out) + "\n"


def initial_workflow(profile: dict, result: dict) -> dict:
    today = now()[:10]
    return {
        "version": 1,
        "seeded_at": now(),
        "signals": profile["signals"],
        "core": dict(DEFAULT_CORE),
        "commands": profile["commands"],
        "practice": [
            {"id": s["id"], "source": s["source"], "reason": s["reason"], "added": today}
            | ({"authored_by": "agent"} if s.get("authored") else {})
            for s in result["selected"]
        ],
    }


# ---------- commands ----------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["plan", "apply", "add", "remove", "render"])
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--answers", type=Path)
    ap.add_argument("--catalog", type=Path, action="append", default=[], help="an org catalogue folder")
    ap.add_argument("--practice")
    ap.add_argument("--reason", default="")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--by", default="", help="who approved the change")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        catalog = load_catalog(layers(root, args.catalog))
        if args.command in ("plan", "apply"):
            profile = probe_mod.probe(root)
            result = plan(profile, load_answers(args.answers), catalog)
            workflow = initial_workflow(profile, result)
            if args.command == "plan":
                print(proposal(profile, result, catalog, workflow), end="")
                return 1 if budget_errors(workflow, catalog) else 0
            if (root / CONFIG).is_file():
                raise ComposeError(f"{CONFIG} exists: this repo is seeded. Use add, remove or render.")
            notes = render(root, workflow, catalog, set(profile["signals"]))
            write_workflow(root, workflow)
            log(root, "seed", "*", "first seeding", baseline=profile["history"], signals=profile["signals"], by=args.by)
            for p in workflow["practice"]:
                mark = {"authored_by": "agent"} if p.get("authored_by") else {}
                log(root, "add", p["id"], p["reason"], source=p["source"], by=args.by, **mark)
            for c in result["candidates"]:
                if c["id"] in result["declined"]:
                    log(root, "decline", c["id"], result["declined"][c["id"]] or "declined at seeding", by=args.by)
            print(f"seeded {len(workflow['practice'])} practice(s) + core; see {CONFIG} and {LEDGER}")
        else:
            workflow = read_workflow(root)
            ids = [p["id"] for p in workflow["practice"]]
            if args.command == "add":
                if not args.practice or not args.reason.strip():
                    raise ComposeError("add needs --practice and --reason (the failure that was seen)")
                if args.practice not in catalog:
                    raise ComposeError(f"{args.practice} is not in the catalogue; write it in {REPO_CATALOG}/ first")
                if args.practice in ids:
                    raise ComposeError(f"{args.practice} is already part of the workflow")
                workflow["practice"].append(
                    {"id": args.practice, "source": "grow", "reason": args.reason.strip(), "added": now()[:10]}
                    | ({"authored_by": "agent"} if authored(catalog[args.practice]) else {})
                )
            elif args.command == "remove":
                if args.practice not in ids or not args.reason.strip():
                    raise ComposeError("remove needs a --practice that is in the workflow and a --reason")
                workflow["practice"] = [p for p in workflow["practice"] if p["id"] != args.practice]
            notes = render(root, workflow, catalog, set(workflow.get("signals", [])))
            if args.command != "render":
                write_workflow(root, workflow)
                mark = {"authored_by": "agent"} if authored(catalog.get(args.practice, {})) else {}
                log(root, args.command, args.practice, args.reason.strip(), evidence=args.evidence, by=args.by, **mark)
                print(f"{args.command}: {args.practice}; logged in {LEDGER}")
            else:
                print("rendered from " + str(CONFIG))
        for n in notes:
            print(n)
    except ComposeError as e:
        print(f"compose: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
