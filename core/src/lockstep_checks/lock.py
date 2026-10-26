"""Find where a spec's tests were locked: the commit where the test PR merged into the feature branch.

Red tests never reach main (Mohammed's rule: no broken code on main). The test PR merges into
``feature/<id>-<slug>``, the implementation follows on that branch, and only the green result
merges to main. So "locked" cannot mean "exists on main". A test is locked once it exists at the
lock commit: the first commit on the feature branch's own line since main (first parents only)
whose status.yml says tests-locked. Following first parents skips the test branch's own commits,
so review fixes inside the test PR stay allowed, whether the test PR is merged or squashed.

Only feature branches have a lock commit. On a test branch the tests are still under review.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from .config import Config
from .spec import Resolution
from .status import SpecStatusError, parse_status

LOCKED_BRANCH_KIND = "feature"


def branch_tip(env: Mapping[str, str] | None = None) -> str:
    """The PR's own last commit. In an Azure Pipelines PR build HEAD is a merge with the target branch."""
    env = os.environ if env is None else env
    return env.get("SYSTEM_PULLREQUEST_SOURCECOMMITID") or "HEAD"


def lock_commit(root: Path, base: str, spec: Resolution, cfg: Config, tip: str = "HEAD") -> str | None:
    """The commit that locked the spec's tests on this feature branch, or None if there is none since ``base``."""
    if spec.state != "found" or not (spec.branch or "").startswith(f"{LOCKED_BRANCH_KIND}/") or spec.spec_dir is None:
        return None
    rel = (spec.spec_dir / "status.yml").relative_to(root).as_posix()
    log = _git(root, "log", "--first-parent", "--reverse", "--format=%H", f"{base}..{tip}", "--", rel)
    for sha in (log or "").split():
        text = _git(root, "show", f"{sha}:{rel}")
        try:
            if text is not None and parse_status(text, cfg).tests_locked:
                return sha
        except SpecStatusError:
            continue  # a broken status.yml in history does not lock anything; HEAD's is validated elsewhere
    return None


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None
