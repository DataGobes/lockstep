"""Evidence files for the trust summary: what each producer writes, and the Azure DevOps client."""

import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from lockstep_checks import evidence, mutation_report
from lockstep_checks.report import Finding, emit
from lockstep_checks.trust_summary import AdoError, AdoThreads

SRC = Path(__file__).resolve().parents[1] / "src"


def test_checks_write_their_findings_when_asked(tmp_path):
    env = {evidence.DIR_ENV: str(tmp_path)}
    emit([Finding("error", "modifies a locked test", "tests/test_x.py")], "check_test_tamper", env, io.StringIO())
    emit([], "check_pr_size", env, io.StringIO())
    emit([Finding("warning", "score")], "mutation_report", env, io.StringIO())  # not a check
    data = json.loads((tmp_path / "checks.json").read_text())
    assert data["schema_version"] == 1 and data["status"] == "measured"
    assert set(data["signals"]["checks"]) == {"test_tamper", "pr_size"}
    assert data["signals"]["checks"]["test_tamper"]["findings"][0]["path"] == "tests/test_x.py"


def test_checks_write_nothing_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    emit([], "check_pr_size", {}, io.StringIO())
    assert list(tmp_path.iterdir()) == []


def test_coverage_from_diff_cover():
    assert evidence.coverage_from_diff_cover({"total_percent_covered": 86, "total_num_lines": 50}, 80) == {
        "percent": 86.0,
        "minimum": 80,
    }
    assert evidence.coverage_from_diff_cover({"total_percent_covered": 100, "total_num_lines": 0}, 80) is None


def test_coverage_merges_into_the_quality_file(tmp_path, monkeypatch):
    evidence.update(tmp_path, "quality", {"tests": {"t::a": {"acs": [], "result": "passes", "detail": ""}}})
    report = tmp_path / "diff-cover.json"
    report.write_text(json.dumps({"total_percent_covered": 75, "total_num_lines": 4}))
    monkeypatch.setenv(evidence.DIR_ENV, str(tmp_path))
    assert evidence.main(["coverage", "--report", str(report), "--minimum", "80"]) == 0
    signals = json.loads((tmp_path / "quality.json").read_text())["signals"]
    assert signals["coverage_changed_lines"] == {"percent": 75.0, "minimum": 80.0}
    assert "t::a" in signals["tests"]


def test_mutation_counts(tmp_path, monkeypatch):
    monkeypatch.setenv(evidence.DIR_ENV, str(tmp_path))
    statuses = ["killed", "killed", "timeout", "survived", "no tests"]
    mutation_report._record([mutation_report.Mutant(f"m{i}", s, None, None) for i, s in enumerate(statuses)])
    m = json.loads((tmp_path / "mutation.json").read_text())["signals"]["mutation"]
    assert m == {"caught": 3, "survived": 1, "no_tests": 1, "total": 5}


def test_pytest_plugin_writes_the_tests_to_the_quality_file(tmp_path):
    (tmp_path / "test_x.py").write_text(
        "import pytest\n\n@pytest.mark.ac('0042/AC-001')\ndef test_a():\n    assert 1 == 2\n\ndef test_b():\n    pass\n"
    )
    out = tmp_path / "evidence"
    env = dict(os.environ, PYTHONPATH=str(SRC), **{evidence.DIR_ENV: str(out)})
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "lockstep_checks.pytest_evidence", "-p", "no:cacheprovider"]
    subprocess.run(cmd, cwd=tmp_path, env=env, check=False, capture_output=True)
    tests = json.loads((out / "quality.json").read_text())["signals"]["tests"]
    assert tests["test_x.py::test_a"]["acs"] == ["0042/AC-001"]
    assert tests["test_x.py::test_a"]["result"] == "red"
    assert tests["test_x.py::test_b"]["result"] == "passes"


ENV = {
    "SYSTEM_COLLECTIONURI": "https://dev.azure.com/example/",
    "SYSTEM_TEAMPROJECTID": "proj",
    "BUILD_REPOSITORY_ID": "repo",
    "SYSTEM_PULLREQUEST_PULLREQUESTID": "7",
    "SYSTEM_ACCESSTOKEN": "token",
}


def test_ado_client_calls_the_threads_api():
    calls = []

    def fetch(req):
        calls.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None))
        return json.dumps({"id": 12, "value": []}).encode()

    client = AdoThreads(ENV, fetch)
    client.list_threads()
    client.create_thread("hello", "closed")
    client.update_comment(12, 1, "again")
    base = "https://dev.azure.com/example/proj/_apis/git/repositories/repo/pullRequests/7/threads"
    assert [(m, u) for m, u, _ in calls] == [
        ("GET", f"{base}?api-version=7.1"),
        ("POST", f"{base}?api-version=7.1"),
        ("PATCH", f"{base}/12/comments/1?api-version=7.1"),
    ]
    assert calls[1][2]["status"] == "closed" and calls[2][2] == {"content": "again"}


def test_ado_client_reports_http_errors_and_missing_variables():
    def fetch(req):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"TF401027"))

    with pytest.raises(AdoError, match="TF401027") as e:
        AdoThreads(ENV, fetch).list_threads()
    assert e.value.status == 403
    with pytest.raises(AdoError, match="SYSTEM_ACCESSTOKEN"):
        AdoThreads({}, fetch)
