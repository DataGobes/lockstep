#!/usr/bin/env python3
"""Check Copilot code review instruction files against the rule-quality guardrails.

    python3 lint_instructions.py [--root REPO] [--project-instructions FILE ...] [--json] [FILES ...]

With no FILES, lints every .github|.azuredevops copilot-instructions.md and
instructions/**/*.instructions.md in the repo. Exits 1 if any ERROR is found.
Stdlib only.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_LINES = 1000
WARN_LINES = 200
WARN_CHARS_REPO_WIDE = 4000
RULE_BUDGET = (10, 20)
MAX_RULE_CHARS = 300
DUP_RATIO = 0.75

# Instruction types Copilot code review does not support (GitHub docs, "What not to include").
UNSUPPORTED = [
    (r"\bemoji", "comment formatting (emoji) is not supported"),
    (r"\b(bold|italic|markdown)\b.*\b(comment|feedback|review)s?\b|\b(comment|feedback|review)s?\b.*\b(bold|italic)\b",
     "comment formatting is not supported"),
    (r"\bformat (of )?(the |your )?(review )?comments?\b|\bcomment format\b", "comment formatting is not supported"),
    (r"\b(pr|pull request) (overview|summary|description)\b|\boverview comment\b", "the PR overview cannot be changed"),
    (r"\bblock(ing)? (the )?(pr|pull request|merge|merging)\b|\bprevent (the )?merg|\b(approve|reject) the (pr|pull request)\b|\brequest changes\b",
     "Copilot cannot block, approve or reject a PR"),
    (r"\bchangelog\b.*\b(generate|write|add)\b|\b(generate|write|add)\b.*\bchangelog entr", "changing Copilot's core function is not supported"),
]
VAGUE = [
    r"\bbest practices?\b", r"\bSOLID\b", r"\bclean code\b", r"\bbe (more )?(accurate|consistent|thorough|careful)\b",
    r"\bdon'?t miss\b", r"\bhigh[- ]quality\b", r"\bwhere (appropriate|applicable|needed)\b", r"\bas (appropriate|needed)\b",
    r"\bfollow (the )?(standard|existing|usual|common) (conventions|patterns|practices)\b", r"\bmaintainab(le|ility)\b",
    r"\breadab(le|ility)\b", r"\bproperly\b", r"\bgood (naming|names|practice)\b", r"\bDRY\b", r"\bKISS\b", r"\bYAGNI\b",
]
STOPWORDS = set("a an the and or of to in on for with from by as at is are be must should never not no all any every "
                "each use using this that it its only do don't dont avoid always new".split())
LINK = re.compile(r"https?://|\]\((?!#)[^)]+\)")
BULLET = re.compile(r"^(?:[-*+]|\d+[.)])\s+(.*)")


def tracked_files(root):
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout
        return [f for f in out.splitlines() if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file() and ".git" not in p.parts]


def glob_to_regex(pattern):
    """Glob semantics from the Copilot docs: '*' stays in one folder, '**/' spans zero or more folders, {a,b} alternation."""
    i, out = 0, ""
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        elif c == "{":
            j = pattern.find("}", i)
            if j == -1:
                out += re.escape(c)
                i += 1
            else:
                out += "(?:" + "|".join(re.escape(x) for x in pattern[i + 1:j].split(",")) + ")"
                i = j + 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(out + r"\Z")


def split_apply_to(value):
    """Split on commas that are not inside {...}."""
    parts, depth, cur = [], 0, ""
    for ch in value:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def parse(path):
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    front, body_start = {}, 0
    if lines and lines[0].strip() == "---":
        for k, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start = k + 1
                break
            m = re.match(r"^(\w+)\s*:\s*(.*)$", line)
            if m:
                front[m.group(1)] = m.group(2).strip()
    rules, prose, in_code = [], [], False
    for n, line in enumerate(lines[body_start:], body_start + 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = BULLET.match(line)
        if m:
            rules.append((n, m.group(1).strip()))
        elif line.strip() and not line.lstrip().startswith(("#", "<!--", "|", ">")) and not line.startswith((" ", "\t")):
            prose.append((n, line.strip()))
    return text, lines, front, rules, prose, body_start


def norm(s):
    s = re.sub(r"`[^`]*`", lambda m: m.group(0).lower(), s)
    return re.sub(r"[^a-z0-9_`. ]+", " ", s.lower()).strip()


def similar(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    # Containment of content words catches a shorter rewording of an upstream rule.
    ta, tb = set(a.split()) - STOPWORDS, set(b.split()) - STOPWORDS
    small = min(len(ta), len(tb))
    contained = len(ta & tb) / small if small >= 3 else 0.0
    return max(ratio, contained)


def project_rules(paths):
    rules = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            m = BULLET.match(line.strip())
            text = (m.group(1) if m else line).strip()
            if len(text) > 15 and not text.startswith("#"):
                rules.append((Path(p).name, text))
    return rules


def discover(root):
    found = []
    for base in (".github", ".azuredevops"):
        f = root / base / "copilot-instructions.md"
        if f.exists():
            found.append(f)
        found += sorted((root / base / "instructions").rglob("*.md")) if (root / base / "instructions").is_dir() else []
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--root", default=".")
    ap.add_argument("--project-instructions", nargs="*", default=[], help="project/org-level instruction text files")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(subprocess.run(["git", "-C", args.root, "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True).stdout.strip() or args.root).resolve()
    files = [Path(f).resolve() for f in args.files] or discover(root)
    tracked = tracked_files(root)
    upstream = project_rules(args.project_instructions)
    issues, all_rules, summary = [], [], []

    def report(level, path, line, msg):
        issues.append({"level": level, "file": str(Path(path).relative_to(root)) if str(path).startswith(str(root)) else str(path),
                       "line": line, "message": msg})

    for path in files:
        rel = path.relative_to(root).as_posix() if str(path).startswith(str(root)) else path.as_posix()
        text, lines, front, rules, prose, body_start = parse(path)
        is_repo_wide = rel.endswith("copilot-instructions.md") and "/instructions/" not in rel
        matched = None

        if not is_repo_wide:
            if not rel.endswith(".instructions.md"):
                report("ERROR", path, 1, "path-scoped files must be named NAME.instructions.md, or Copilot ignores them")
            if "applyTo" not in front:
                report("ERROR", path, 1, "missing `applyTo` frontmatter; Copilot skips path-scoped files without it")
            else:
                raw = front["applyTo"]
                if not re.fullmatch(r'"[^"]*"|\'[^\']*\'', raw):
                    report("WARN", path, 2, "quote the applyTo value, e.g. applyTo: \"**/*.py\"")
                patterns = split_apply_to(raw.strip("\"'"))
                matched = set()
                for pat in patterns:
                    rx = glob_to_regex(pat)
                    hits = {f for f in tracked if rx.match(f)}
                    if not hits:
                        report("WARN", path, 2, f"applyTo pattern '{pat}' matches no tracked file; check the glob")
                    matched |= hits
            if front.get("excludeAgent", "").strip("\"'") == "code-review":
                report("WARN", path, 2, "excludeAgent: code-review means code review will NOT read this file")
        elif front:
            report("WARN", path, 1, "repo-wide copilot-instructions.md does not need frontmatter")

        if len(lines) > MAX_LINES:
            report("ERROR", path, MAX_LINES, f"{len(lines)} lines; keep each file well under {MAX_LINES}")
        elif len(lines) > WARN_LINES:
            report("WARN", path, WARN_LINES, f"{len(lines)} lines; aim for under {WARN_LINES} so every rule gets attention")
        if is_repo_wide and len(text) > WARN_CHARS_REPO_WIDE:
            report("WARN", path, 1, f"{len(text)} chars; put the highest-value rules in the first {WARN_CHARS_REPO_WIDE} characters")

        in_code = False
        for n, line in enumerate(lines[body_start:], body_start + 1):
            if line.lstrip().startswith(("```", "~~~")):
                in_code = not in_code
                continue
            if LINK.search(line) and not in_code:
                report("ERROR", path, n, "external link; Copilot code review does not follow links, inline the content")

        for n, rule in rules + prose:
            low = rule.lower()
            for rx, why in UNSUPPORTED:
                if re.search(rx, low):
                    report("ERROR", path, n, f"unsupported instruction ({why}): {rule[:80]}")
                    break
            for rx in VAGUE:
                if re.search(rx, rule, re.I):
                    report("WARN", path, n, f"vague wording '{re.search(rx, rule, re.I).group(0)}'; make it checkable in a diff: {rule[:80]}")
                    break
        for n, rule in rules:
            if len(rule) > MAX_RULE_CHARS:
                report("WARN", path, n, f"rule is {len(rule)} chars; split it or move detail into an example")
            for src, up in upstream:
                if similar(rule, up) >= DUP_RATIO:
                    report("WARN", path, n, f"near-duplicate of project-wide rule in {src}: \"{up[:80]}\"")
                    break
            for other_path, m, other in all_rules:
                if similar(rule, other) >= DUP_RATIO:
                    report("WARN", path, n, f"near-duplicate of {other_path}:{m}")
                    break
            all_rules.append((rel, n, rule))
        summary.append({"file": rel, "kind": "repo-wide" if is_repo_wide else "path-scoped", "rules": len(rules),
                        "lines": len(lines), "chars": len(text), "applyTo": front.get("applyTo"),
                        "matched_files": None if matched is None else len(matched)})

    total = len(all_rules)
    if files and not RULE_BUDGET[0] <= total <= RULE_BUDGET[1]:
        issues.append({"level": "WARN", "file": "(all)", "line": 0,
                       "message": f"{total} rules in total; start with {RULE_BUDGET[0]}-{RULE_BUDGET[1]} and grow from review evidence"})

    errors = sum(i["level"] == "ERROR" for i in issues)
    if args.json:
        json.dump({"files": summary, "total_rules": total, "issues": issues, "errors": errors}, sys.stdout, indent=2)
        print()
    else:
        if not files:
            print("No instruction files found.")
        for s in summary:
            scope = f" applyTo={s['applyTo']} -> {s['matched_files']} files" if s["applyTo"] else ""
            print(f"{s['file']}: {s['rules']} rules, {s['lines']} lines, {s['chars']} chars{scope}")
        print(f"Total rules: {total}")
        for i in issues:
            print(f"{i['level']:5} {i['file']}:{i['line']}  {i['message']}")
        print(f"{errors} error(s), {len(issues) - errors} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
