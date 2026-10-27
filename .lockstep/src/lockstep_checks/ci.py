"""The PR a CI run is building, read from Azure Pipelines or GitHub Actions variables.

Every check asks this module, so supporting another CI system means one change here.
Outside a PR build every function returns "" and callers fall back to git.

  Azure Pipelines  SYSTEM_PULLREQUEST_TARGETBRANCH / _SOURCEBRANCH / _SOURCECOMMITID, BUILD_SOURCEBRANCH
  GitHub Actions   GITHUB_BASE_REF / GITHUB_HEAD_REF (pull_request events only), the head sha from GITHUB_EVENT_PATH
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _branch(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


def on_azure(env: Mapping[str, str] | None = None) -> bool:
    return _env(env).get("TF_BUILD", "").lower() == "true"


def on_github(env: Mapping[str, str] | None = None) -> bool:
    return _env(env).get("GITHUB_ACTIONS", "").lower() == "true"


def target_branch(env: Mapping[str, str] | None = None) -> str:
    """The branch the PR merges into, without refs/heads/; "" outside a PR build."""
    env = _env(env)
    return _branch(env.get("SYSTEM_PULLREQUEST_TARGETBRANCH", "") or env.get("GITHUB_BASE_REF", ""))


def source_branch(env: Mapping[str, str] | None = None) -> str:
    """The PR's own branch; "" when CI does not say (HEAD is then a detached merge commit or a plain checkout)."""
    env = _env(env)
    for name in ("SYSTEM_PULLREQUEST_SOURCEBRANCH", "BUILD_SOURCEBRANCH"):
        ref = env.get(name, "")
        if ref.startswith("refs/heads/"):
            return _branch(ref)
    if env.get("GITHUB_HEAD_REF"):
        return env["GITHUB_HEAD_REF"]
    ref = env.get("GITHUB_REF", "")  # a push build
    return _branch(ref) if ref.startswith("refs/heads/") else ""


def source_commit(env: Mapping[str, str] | None = None) -> str:
    """The PR's last commit. In a PR build both systems check out a merge with the target branch, not this."""
    env = _env(env)
    if env.get("SYSTEM_PULLREQUEST_SOURCECOMMITID"):
        return env["SYSTEM_PULLREQUEST_SOURCECOMMITID"]
    if env.get("GITHUB_HEAD_REF") and env.get("GITHUB_EVENT_PATH"):
        try:
            event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            sha = event["pull_request"]["head"]["sha"]
        except (OSError, ValueError, KeyError, TypeError):
            return ""
        return sha if isinstance(sha, str) else ""
    return ""
