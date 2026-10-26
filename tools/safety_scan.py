#!/usr/bin/env python3
"""Scan what Lockstep ships into other teams' repos for secrets, network access, risky code and hidden text.

  python3 tools/safety_scan.py        # exit 1 on any finding; check_release.py runs it too

Shipped means the plugins (skills, their scripts), the core that bootstrap vendors into .lockstep/ (checks, hooks,
pipelines) and the templates. Other teams install these and run the hooks on every agent action, so a leaked key,
an unexpected network call or a hidden instruction in a SKILL.md would spread to every repo. Findings that are
intended are listed in ALLOWED with the reason. After Tessl's security scores for registry skills. Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SHIPPED = ("plugins", "core/src", "core/hooks", "core/pipelines", "templates")
SKIP_PARTS = {"__pycache__", "tests", "evals", ".egg-info"}
TEXT_SUFFIXES = {".py", ".sh", ".md", ".yml", ".yaml", ".json", ".toml", ".txt", ".sql", ".csv", ".jsonl"}

# (kind, pattern, applies to suffixes or None for all text, what it means)
_RULES: tuple[tuple[str, re.Pattern[str], set[str] | None, str], ...] = tuple(
    (kind, re.compile(pattern), suffixes, why)
    for kind, pattern, suffixes, why in (
        ("secret", r"\bAKIA[0-9A-Z]{16}\b", None, "looks like an AWS access key"),
        ("secret", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", None, "contains a private key"),
        ("secret", r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}\b", None, "looks like a GitHub token"),
        ("secret", r"\bxox[abps]-[A-Za-z0-9-]{10,}\b", None, "looks like a Slack token"),
        ("secret", r"\bsk-[A-Za-z0-9]{32,}\b", None, "looks like an API key"),
        (
            "secret",
            (
                r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"](?![$<{]|example|test|dummy|x+['\"])"
                r"[^'\"\s]{12,}['\"]"
            ),
            None,
            "assigns what looks like a credential",
        ),
        (
            "network",
            r"^\s*(?:import|from)\s+(?:urllib\.request|http\.client|requests|httpx|aiohttp|socket|ftplib|smtplib)\b",
            {".py"},
            "opens network connections",
        ),
        ("network", r"(?:^|[\s;&|(])(?:curl|wget|nc|Invoke-WebRequest)\s", {".sh"}, "downloads or sends data"),
        ("risky", r"\bshell\s*=\s*True\b", {".py"}, "runs a shell command string"),
        ("risky", r"\bos\.(?:system|popen)\(", {".py"}, "runs a shell command string"),
        ("risky", r"(?<![\w.])(?:eval|exec)\(", {".py"}, "evaluates code from a string"),
        ("risky", r"\bpickle\.loads?\(", {".py"}, "unpickles data, which can run code"),
        (
            "hidden",
            "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]",
            None,
            "has invisible or bidi characters",
        ),
    )
)

# (path, kind) -> why it is intended
ALLOWED: dict[tuple[str, str], str] = {
    ("core/src/lockstep_checks/ado_pr_title.py", "network"): "reads the PR title from the Azure DevOps REST API in CI",
}


def shipped_files(root: Path):
    for top in SHIPPED:
        base = root / top
        for path in sorted(base.rglob("*")) if base.is_dir() else []:
            rel = path.relative_to(root)
            if path.is_file() and not (set(rel.parts) & SKIP_PARTS or any(p.endswith(".egg-info") for p in rel.parts)):
                yield path


def scan(root: Path) -> list[str]:
    findings = []
    for path in shipped_files(root):
        rel = path.relative_to(root).as_posix()
        if path.suffix not in TEXT_SUFFIXES and path.name != "run-hook.sh":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"{rel}: not UTF-8 text; shipped files must be readable")
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            for kind, pattern, suffixes, why in _RULES:
                if suffixes is not None and path.suffix not in suffixes:
                    continue
                if (rel, kind) in ALLOWED or not pattern.search(line):
                    continue
                findings.append(f"{rel}:{n}: {kind}: {why}")
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args(argv)
    findings = scan(args.root)
    print("\n".join(findings) if findings else "safety scan: nothing found in shipped files")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
