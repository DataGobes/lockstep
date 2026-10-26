"""One Lockstep summary comment per PR: can this change be trusted? (spec 0001)

Each PR job writes what it measured to ``lockstep-evidence/<producer>.json`` (see ``evidence``). This module merges
those files with git history and the base branch's ``lockstep.toml``, renders the summary, and posts it on the Azure
DevOps PR, replacing its own comment on later runs. It never reads the PR description. A signal without evidence is
"not measured", never clean.

  python -m lockstep_checks.trust_summary [--root .] [--evidence lockstep-evidence] [--json] [--post]

Without ``--post`` it prints the summary, the same text the pipeline posts. With ``--post`` (the pipeline) it posts
the comment and keeps a copy as a pipeline artifact; it never fails the run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

from .cli import TITLE_ENV, config_at
from .config import Config
from .evidence import SCHEMA_VERSION
from .gitdiff import GitError, changed_files
from .lock import branch_tip, lock_commit
from .paths import matches, matches_any
from .red_phase import expected_red, is_test_file
from .spec import SpecError, current_branch, resolve_spec
from .specdoc import parse_spec

MARKER = "<!-- lockstep-trust-summary -->"
EVIDENCE_DIR = "lockstep-evidence"
FOLD_ABOVE_ROWS = 10
API_VERSION = "7.1"


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

    @property
    def into_feature_branch(self) -> bool:
        return self.target.startswith("feature/")

    @property
    def test_change(self) -> bool:
        return self.title.lstrip().startswith("[test-change]")


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
    """Every evidence file under ``folder`` (artifacts download into subfolders); an unreadable one becomes an error."""
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            data = f"{e}"
        if not isinstance(data, dict) or not isinstance(data.get("producer"), str):
            why = data if isinstance(data, str) else "not an evidence file"
            data = {"producer": path.stem, "status": "error", "reason": f"unreadable evidence file {path.name}: {why}"}
        found.append(data)
    return found


@dataclass(frozen=True)
class _Source:
    signals: dict[str, Any] | None  # None when not measured
    reason: str = ""


def _sources(evidence: list[dict[str, Any]]) -> dict[str, _Source]:
    sources: dict[str, _Source] = {}
    for e in evidence:
        producer = e["producer"]
        if e.get("schema_version") != SCHEMA_VERSION and e.get("status") != "error":
            sources[producer] = _Source(None, f"unknown evidence format (schema_version {e.get('schema_version')})")
        elif e.get("status") != "measured":
            sources[producer] = _Source(None, e.get("reason") or f"the {producer} job reported {e.get('status')}")
        else:
            sources[producer] = _Source(e.get("signals") or {})
    return sources


def _source(sources: dict[str, _Source], producer: str, job: str) -> _Source:
    return sources.get(producer) or _Source(None, f"no evidence from the {job} step")


# How a test's raw result (from the pytest plugin) shows in the summary.
_SHOWN = {"passes": "passed", "skipped": "skipped", "not-run": "not_run"}
_BAD = {"failed", "red_wrong_reason", "skipped", "not_run"}


def _result(node: str, raw: str, ctx: Context) -> str:
    excused = ctx.into_feature_branch and node.split("::", 1)[0] in ctx.expected_red
    if raw in _SHOWN:
        return _SHOWN[raw]
    if excused:
        return "red_expected" if raw == "red" else "red_wrong_reason"
    return "failed"  # red, wrong-reason, check, collection-error


def _is_bad(node: str, result: str, ctx: Context) -> bool:
    excused = ctx.into_feature_branch and node.split("::", 1)[0] in ctx.expected_red
    return result in _BAD or (excused and result == "passed")


def _signal(name: str, label: str, state: str, text: str, next_step: str | None = None, **extra: Any) -> dict:
    return {"name": name, "label": label, "state": state, "text": text, "next_step": next_step, "reason": "", **extra}


def _unmeasured(name: str, label: str, reason: str) -> dict:
    s = _signal(name, label, "not_measured", f"not measured: {reason}")
    s["reason"] = reason
    return s


def _tests_signal(src: _Source, ctx: Context, criteria: list[dict], bad_tests: list[str]) -> dict:
    if src.signals is None or "tests" not in src.signals:
        return _unmeasured("tests", "Tests", src.reason or "the quality job recorded no test results")
    counted = "red_expected" if ctx.into_feature_branch else "passed"
    met = sum(any(t["result"] == counted for t in c["tests"]) for c in criteria)
    untested = [c["id"] for c in criteria if not c["tests"]]
    if ctx.into_feature_branch and criteria:
        count = f"{met} of {len(criteria)} criteria have a test that is red as expected"
    elif criteria:
        count = f"{met} of {len(criteria)} criteria have a passing test"
    else:
        count = "all tests pass" if not bad_tests else ""
    problems = []
    if bad_tests:
        problems.append(f"{len(bad_tests)} test{'s' if len(bad_tests) != 1 else ''} not as expected")
    if untested:
        problems.append(f"no test for {', '.join(untested)}")
    if not problems and (not criteria or met == len(criteria)):
        return _signal("tests", "Tests", "clean", count, met=met, total=len(criteria))
    if ctx.into_feature_branch:
        step = "Make each spec test fail on an assertion or NotImplementedError, and give every criterion a test."
    else:
        step = "Fix the code until every test passes, and add a test for each criterion that has none."
    text = "; ".join(filter(None, [count, *problems]))
    return _signal("tests", "Tests", "not_clean", text, step, met=met, total=len(criteria))


def _coverage_signal(src: _Source) -> dict:
    cov = (src.signals or {}).get("coverage_changed_lines")
    if src.signals is None or not cov:
        return _unmeasured("coverage", "Coverage", src.reason or "changed-line coverage was not measured in this run")
    percent, minimum = cov["percent"], cov["minimum"]
    text = f"{percent:g}% of changed lines covered (minimum {minimum:g}%)"
    if percent >= minimum:
        return _signal("coverage", "Coverage", "clean", text, percent=percent, minimum=minimum)
    step = "Add tests for the changed lines the coverage report lists."
    return _signal("coverage", "Coverage", "not_clean", text, step, percent=percent, minimum=minimum)


def _lock_signal(src: _Source) -> dict:
    lock = (src.signals or {}).get("lock")
    if src.signals is None or not lock:
        return _unmeasured("lock", "Lock", src.reason or "no lock commit recorded")
    commit, date, changed = lock["commit"], lock["date"], sorted(lock.get("changed_since", []))
    where = f"tests locked at {commit[:7]} on {date}"
    if not changed:
        return _signal(
            "lock",
            "Lock",
            "clean",
            f"{where}; no protected file changed since",
            commit=commit,
            date=date,
            changed_since=[],
        )
    step = "Revert the change to the locked tests, or retitle the PR [test-change] for the test reviewers."
    text = f"{where}; changed since: {', '.join(changed)}"
    return _signal("lock", "Lock", "not_clean", text, step, commit=commit, date=date, changed_since=changed)


def _tamper_signal(src: _Source, ctx: Context) -> dict:
    checks = (src.signals or {}).get("checks", {})
    if src.signals is None or "test_tamper" not in checks:
        return _unmeasured("tamper", "Test tamper", src.reason or "the test-tamper check left no result")
    tamper = checks["test_tamper"]
    findings = tamper.get("findings", [])
    if (tamper.get("test_change") or ctx.test_change) and findings:
        paths = sorted({f["path"] for f in findings if f.get("path")})
        text = f"approved test change ([test-change]): {', '.join(paths) or 'see the check output'}"
        return _signal("tamper", "Test tamper", "approved_change", text, approved_changes=paths)
    blocking = [f for f in findings if f.get("level") == "error" or f.get("would_block")]
    if not blocking:
        return _signal("tamper", "Test tamper", "clean", "no locked test weakened")
    where = ", ".join(sorted({f.get("path") or f.get("message", "") for f in blocking}))
    step = "Undo the change to the protected tests, or retitle the PR [test-change] if it is deliberate."
    return _signal("tamper", "Test tamper", "not_clean", f"{len(blocking)} finding(s): {where}", step)


def _mutation_signal(src: _Source) -> dict:
    m = (src.signals or {}).get("mutation")
    if src.signals is None or not m:
        return _unmeasured("mutation", "Mutation", src.reason or "the mutation job left no score")
    if not m.get("total"):
        return _unmeasured("mutation", "Mutation", "no mutants were tested")
    score = round(100 * m["caught"] / m["total"])
    missed = m.get("survived", 0) + m.get("no_tests", 0)
    text = f"mutation score {score}%: {m['caught']} of {m['total']} mutants caught, {missed} missed (report only)"
    return _signal("mutation", "Mutation", "info", text, score=score, missed=missed)


_ICON = {"clean": "✅", "info": "ℹ️", "not_clean": "❌", "approved_change": "⚠️", "not_measured": "➖"}
_ORDER = {"not_clean": 0, "approved_change": 1, "not_measured": 2, "clean": 3, "info": 4}
_SHOWN_RESULT = {
    "passed": "passed",
    "failed": "failed",
    "red_expected": "red, as expected",
    "red_wrong_reason": "red for the wrong reason",
    "skipped": "skipped",
    "not_run": "not run",
}


def render(evidence: list[dict[str, Any]], ctx: Context) -> Summary:
    sources = _sources(evidence)
    quality = _source(sources, "quality", "quality")
    tests: dict[str, dict] = (quality.signals or {}).get("tests", {})
    results = {node: _result(node, t["result"], ctx) for node, t in tests.items()}

    criteria = []
    if ctx.lane is None:
        for ac in ctx.criteria:
            if ac in ctx.superseded:
                continue
            mine = [{"node": n, "result": results[n]} for n, t in tests.items() if ac in t.get("acs", [])]
            criteria.append({"id": ac, "tests": mine})
    bad_tests = [n for n, r in results.items() if _is_bad(n, r, ctx)]

    signals = [_tests_signal(quality, ctx, criteria, bad_tests), _coverage_signal(quality)]
    if ctx.spec_id and ctx.branch.startswith("feature/"):
        signals.append(_lock_signal(_source(sources, "lock", "lock")))
    signals.append(_tamper_signal(_source(sources, "checks", "Lockstep checks"), ctx))
    signals.append(_mutation_signal(_source(sources, "mutation", "mutation")))
    signals.sort(key=lambda s: _ORDER[s["state"]])

    clean = all(s["state"] in ("clean", "info") for s in signals)
    lines = [MARKER]
    if clean:
        lines.append(f"**✅ Lockstep: every signal is clean.** {_tests_count(signals)}")
    for s in signals:
        step = f" **Next:** {s['next_step']}" if s["next_step"] else ""
        lines.append(f"- {_ICON[s['state']]} **{s['label']}:** {s['text']}.{step}")

    bugfix = None
    if ctx.lane in ("bugfix", "hotfix"):
        bugfix = {
            "bug_report": ctx.bug_report,
            "tests": [{"node": n, "result": results.get(n, "not_run")} for n in ctx.regression_tests],
        }
    lines += _body(ctx, criteria, bugfix, [n for n in bad_tests if not _in_criteria(n, criteria)], results)

    data = {
        "schema_version": SCHEMA_VERSION,
        "verdict": "clean" if clean else "attention",
        "branch": ctx.branch,
        "target": ctx.target,
        "spec": ctx.spec_id,
        "lane": ctx.lane,
        "signals": signals,
        "criteria": criteria,
        "bugfix": bugfix,
    }
    return Summary(markdown="\n".join(lines) + "\n", data=data)


def _tests_count(signals: list[dict]) -> str:
    tests = next(s for s in signals if s["name"] == "tests")
    return f"{tests['text'][:1].upper()}{tests['text'][1:]}." if tests["text"] else ""


def _in_criteria(node: str, criteria: list[dict]) -> bool:
    return any(t["node"] == node for c in criteria for t in c["tests"])


def _body(ctx: Context, criteria: list[dict], bugfix: dict | None, others: list[str], results: dict) -> list[str]:
    lines = [""]
    if ctx.lane == "chore":
        lines.append("Lane: **chore** (no spec needed).")
    elif bugfix is not None:
        lines.append(f"Lane: **{ctx.lane}**. Bug report: `{bugfix['bug_report'] or 'missing'}`.")
        lines += [f"- Regression test `{t['node']}`: {_SHOWN_RESULT[t['result']]}" for t in bugfix["tests"]]
        if not bugfix["tests"]:
            lines.append("- No regression test found.")
    elif criteria:
        rows = ["| Criterion | Test | Result |", "|---|---|---|"]
        for c in criteria:
            if not c["tests"]:
                rows.append(f"| {c['id']} | no test | ❌ |")
            for t in c["tests"]:
                rows.append(f"| {c['id']} | `{t['node']}` | {_SHOWN_RESULT[t['result']]} |")
        if len(rows) - 2 > FOLD_ABOVE_ROWS:
            lines += [f"<details><summary>{len(criteria)} criteria of spec {ctx.spec_id}</summary>", "", *rows]
            lines += ["", "</details>"]
        else:
            lines += rows
    if others:
        lines += ["", "Other tests not as expected:"]
        lines += [f"- `{n}`: {_SHOWN_RESULT[results[n]]}" for n in others]
    return lines


def lock_evidence(root: Path, base: str, branch: str) -> dict[str, Any]:
    """The ``lock`` producer: the lock commit, its date, and protected files changed since it."""
    cfg = config_at(root, base)
    try:
        spec = resolve_spec(root, branch, cfg)
    except SpecError as e:
        return _lock_unmeasured("error", f"the spec is broken: {e}")
    tip = branch_tip()
    sha = lock_commit(root, base, spec, cfg, tip)
    if sha is None:
        return _lock_unmeasured(
            "skipped", "no lock yet: the tests lock when the test PR merges into the feature branch"
        )
    date = _git(root, "show", "-s", "--format=%cs", sha).strip()
    changed = []
    for line in _git(root, "diff", "--name-status", "--no-renames", sha, tip).splitlines():
        status, _, path = line.partition("\t")
        if status != "A" and matches_any(path, cfg.protect.globs):
            changed.append(path)
    signals = {"lock": {"commit": sha, "date": date, "changed_since": sorted(changed)}}
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": "lock",
        "status": "measured",
        "reason": None,
        "signals": signals,
    }


def _lock_unmeasured(status: str, reason: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "producer": "lock", "status": status, "reason": reason, "signals": {}}


def _git(root: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True, text=True, timeout=30)
    return p.stdout if p.returncode == 0 else ""


def _branch_env(env: Mapping[str, str], name: str) -> str:
    return env.get(name, "").removeprefix("refs/heads/")


def build(root: Path, evidence_dir: Path, env: Mapping[str, str]) -> Summary:
    """The summary for the PR the pipeline variables in ``env`` describe. The PR description is never read."""
    branch = _branch_env(env, "SYSTEM_PULLREQUEST_SOURCEBRANCH") or current_branch(root, env) or ""
    target = _branch_env(env, "SYSTEM_PULLREQUEST_TARGETBRANCH") or "main"
    base = f"origin/{target}"
    cfg = config_at(root, base)
    evidence = load_evidence(evidence_dir)
    ctx = _context(root, cfg, branch, target, base, env.get(TITLE_ENV, ""), evidence)
    if ctx.spec_id and branch.startswith("feature/") and not any(e["producer"] == "lock" for e in evidence):
        evidence.append(lock_evidence(root, "origin/main", branch))
    return render(evidence, ctx)


def _context(
    root: Path, cfg: Config, branch: str, target: str, base: str, title: str, evidence: list[dict[str, Any]]
) -> Context:
    lane = next((kind for kind in ("chore", "bugfix") if branch.startswith(getattr(cfg.lanes, kind))), None)
    if lane is not None:
        return _lane_context(root, cfg, branch, target, base, title, evidence, lane)
    try:
        spec = resolve_spec(root, branch, cfg)
    except SpecError:
        spec = None
    if spec is None or spec.state != "found" or spec.spec_dir is None:
        return Context(branch=branch, target=target, title=title)
    doc = parse_spec((spec.spec_dir / "spec.md").read_text(encoding="utf-8"), cfg.specs.ac_format)
    try:
        red = tuple(expected_red(root, target))
    except GitError:
        red = ()
    return Context(
        branch=branch,
        target=target,
        title=title,
        spec_id=spec.spec_id,
        criteria=tuple(f"{spec.spec_id}/{ac}" for ac in doc.criteria),
        superseded=frozenset(f"{spec.spec_id}/{ac}" for ac in doc.superseded),
        expected_red=red,
    )


def _lane_context(
    root: Path, cfg: Config, branch: str, target: str, base: str, title: str, evidence: list, lane: str
) -> Context:
    if lane == "chore":
        return Context(branch=branch, target=target, title=title, lane="chore")
    try:
        files = changed_files(root, base)
    except GitError:
        files = []
    reports_glob = f"{cfg.lanes.bug_reports_dir.rstrip('/')}/*.md"
    report = next((f.path for f in files if f.status != "D" and matches(f.path, reports_glob)), None)
    new_tests = {f.path for f in files if f.status == "A" and is_test_file(f.path)}
    quality = next((e for e in evidence if e.get("producer") == "quality"), {})
    nodes = [n for n in (quality.get("signals") or {}).get("tests", {}) if n.split("::", 1)[0] in new_tests]
    kind = "hotfix" if branch.startswith("hotfix/") else "bugfix"
    return Context(
        branch=branch, target=target, title=title, lane=kind, bug_report=report, regression_tests=tuple(sorted(nodes))
    )


def post(summary: Summary, client: ThreadClient) -> PostResult:
    """Create the summary thread, or replace the text of the one an earlier run created."""
    for thread in client.list_threads():
        for comment in thread.get("comments") or []:
            if MARKER in (comment.get("content") or ""):
                client.update_comment(thread["id"], comment["id"], summary.markdown)
                return PostResult("updated", thread["id"])
    # Closed, so a branch policy that requires every comment to be resolved never waits on it.
    created = client.create_thread(summary.markdown, "closed")
    return PostResult("created", created["id"])


def publish(summary: Summary, client: ThreadClient, artifact_dir: Path, out: TextIO | None) -> int:
    """Post the summary and keep a copy as an artifact. Always returns 0: the summary never fails a PR."""
    out = sys.stdout if out is None else out
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "lockstep-summary.md").write_text(summary.markdown, encoding="utf-8")
    (artifact_dir / "lockstep-summary.json").write_text(json.dumps(summary.data, indent=2) + "\n", encoding="utf-8")
    try:
        result = post(summary, client)
    except AdoError as e:
        hint = (
            "grant the project's build service 'Contribute to pull requests' on this repository"
            if e.status in (401, 403)
            else "the summary is kept as the lockstep-summary pipeline artifact"
        )
        print(f"##vso[task.logissue type=warning]trust_summary: cannot post the PR comment ({e}); {hint}", file=out)
        return 0
    except (OSError, ValueError, KeyError) as e:  # network trouble or an unexpected response
        print(f"##vso[task.logissue type=warning]trust_summary: cannot post the PR comment ({e})", file=out)
        return 0
    print(f"trust_summary: {result.action} the summary comment (thread {result.thread_id})", file=out)
    return 0


Fetch = Callable[[urllib.request.Request], bytes]


class AdoThreads:
    """The Pull Request Threads REST API, with the job's System.AccessToken."""

    _NEEDED = (
        "SYSTEM_COLLECTIONURI",
        "SYSTEM_TEAMPROJECTID",
        "BUILD_REPOSITORY_ID",
        "SYSTEM_PULLREQUEST_PULLREQUESTID",
    )

    def __init__(self, env: Mapping[str, str], fetch: Fetch | None = None):
        missing = [n for n in (*self._NEEDED, "SYSTEM_ACCESSTOKEN") if not env.get(n)]
        if missing:
            raise AdoError(0, f"missing pipeline variables: {', '.join(missing)}")
        base = env["SYSTEM_COLLECTIONURI"].rstrip("/")
        self._url = (
            f"{base}/{env['SYSTEM_TEAMPROJECTID']}/_apis/git/repositories/{env['BUILD_REPOSITORY_ID']}"
            f"/pullRequests/{env['SYSTEM_PULLREQUEST_PULLREQUESTID']}/threads"
        )
        self._token = env["SYSTEM_ACCESSTOKEN"]
        self._fetch = fetch or _urlopen

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        req = urllib.request.Request(
            f"{self._url}{path}?api-version={API_VERSION}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
        )
        try:
            raw = self._fetch(req)
        except urllib.error.HTTPError as e:
            raise AdoError(e.code, e.read().decode("utf-8", "replace")[:300] or e.reason) from e
        return json.loads(raw) if raw else {}

    def list_threads(self) -> list[dict[str, Any]]:
        return self._call("GET", "").get("value", [])

    def create_thread(self, content: str, status: str) -> dict[str, Any]:
        body = {"comments": [{"parentCommentId": 0, "content": content, "commentType": 1}], "status": status}
        return self._call("POST", "", body)

    def update_comment(self, thread_id: int, comment_id: int, content: str) -> None:
        self._call("PATCH", f"/{thread_id}/comments/{comment_id}", {"content": content})


def _urlopen(req: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    out = sys.stdout if out is None else out
    ap = argparse.ArgumentParser(prog="python -m lockstep_checks.trust_summary", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="repo root (default: current directory)")
    ap.add_argument("--evidence", type=Path, help=f"evidence folder (default: <root>/{EVIDENCE_DIR})")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--post", action="store_true", help="post it on the Azure DevOps PR (in the pipeline)")
    ap.add_argument("--artifact-dir", type=Path, help="where --post keeps a copy (default: <root>/lockstep-summary)")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    evidence = args.evidence or root / EVIDENCE_DIR
    env = os.environ
    if not args.post:
        summary = build(root, evidence, env)
        out.write(json.dumps(summary.data, indent=2) + "\n" if args.json else summary.markdown)
        return 0
    try:
        summary = build(root, evidence, env)
    except Exception as e:  # noqa: BLE001 - the summary reports; it must never fail the PR
        print(f"##vso[task.logissue type=warning]trust_summary: cannot build the summary: {e}", file=out)
        return 0
    try:
        client: ThreadClient = AdoThreads(env)
    except AdoError as e:
        client = _Unreachable(e)  # publish still keeps the artifact and says why nothing was posted
    return publish(summary, client, args.artifact_dir or root / "lockstep-summary", out)


class _Unreachable:
    def __init__(self, error: AdoError):
        self.error = error

    def list_threads(self) -> list[dict[str, Any]]:
        raise self.error

    def create_thread(self, content: str, status: str) -> dict[str, Any]:
        raise self.error

    def update_comment(self, thread_id: int, comment_id: int, content: str) -> None:
        raise self.error


if __name__ == "__main__":
    sys.exit(main())
