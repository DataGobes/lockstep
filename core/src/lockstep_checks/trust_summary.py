"""One Lockstep summary comment per PR: can this change be trusted? (spec 0001)

Each PR job writes what it measured to ``lockstep-evidence/<producer>.json``. This module merges those files with git
history and the base branch's ``lockstep.toml``, renders the summary, and posts it on the Azure DevOps PR, updating
its own comment on later runs. It never reads the PR description. A signal without evidence is "not measured",
never clean.

  python -m lockstep_checks.trust_summary [--root .] [--evidence lockstep-evidence] [--json]

Stubs only: the tests for spec 0001 are written first and fail on NotImplementedError until this is built.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

SCHEMA_VERSION = 1
MARKER = "<!-- lockstep-trust-summary -->"
EVIDENCE_DIR = "lockstep-evidence"


@dataclass(frozen=True)
class Context:
    """What the summary knows about the PR besides the evidence files."""

    branch: str  # the PR's source branch, e.g. feature/0042-churn
    target: str  # the PR's target branch, e.g. main
    title: str = ""
    spec_id: str | None = None
    criteria: tuple[str, ...] = ()  # the active spec's criteria, as full ids: 0042/AC-001
    superseded: frozenset[str] = frozenset()
    expected_red: tuple[str, ...] = ()  # test files red on purpose in a PR into a feature branch (red_phase)
    lane: str | None = None  # chore | bugfix | hotfix, for a branch that needs no spec
    bug_report: str | None = None
    regression_tests: tuple[str, ...] = ()  # node ids of a bugfix's regression tests


@dataclass(frozen=True)
class Summary:
    markdown: str
    data: dict[str, Any] = field(default_factory=dict)  # the JSON form; carries schema_version


@dataclass(frozen=True)
class PostResult:
    action: str  # created | updated
    thread_id: int


class AdoError(RuntimeError):
    """An Azure DevOps REST call failed."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class ThreadClient(Protocol):
    """The Pull Request Threads API, as much of it as the summary needs."""

    def list_threads(self) -> list[dict[str, Any]]: ...

    def create_thread(self, content: str, status: str) -> dict[str, Any]: ...

    def update_comment(self, thread_id: int, comment_id: int, content: str) -> None: ...


def load_evidence(folder: Path) -> list[dict[str, Any]]:
    """Every evidence file in ``folder``; a file that can't be read becomes an error entry for its producer."""
    raise NotImplementedError


def render(evidence: list[dict[str, Any]], ctx: Context) -> Summary:
    raise NotImplementedError


def lock_evidence(root: Path, base: str, branch: str) -> dict[str, Any]:
    """The ``lock`` producer: the lock commit, its date, and protected files changed since it."""
    raise NotImplementedError


def build(root: Path, evidence_dir: Path, env: Mapping[str, str]) -> Summary:
    """The summary for the PR the pipeline variables in ``env`` describe."""
    raise NotImplementedError


def post(summary: Summary, client: ThreadClient) -> PostResult:
    """Create the summary thread, or replace the text of the one an earlier run created."""
    raise NotImplementedError


def publish(summary: Summary, client: ThreadClient, artifact_dir: Path, out: TextIO) -> int:
    """Post the summary and keep a copy as an artifact. Always returns 0: the summary never fails a PR."""
    raise NotImplementedError


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    raise NotImplementedError
