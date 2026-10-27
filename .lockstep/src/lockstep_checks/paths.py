"""Glob matching for repo-relative paths, the same on Python 3.11+ and every OS.

Patterns are anchored at the repo root and use forward slashes:
``*`` matches within one folder, ``**/`` matches zero or more folders, and a
trailing ``/**`` matches everything below a folder.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def matches(path: str, pattern: str) -> bool:
    return _compile(pattern).fullmatch(path.replace("\\", "/")) is not None


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(matches(path, p) for p in patterns)
