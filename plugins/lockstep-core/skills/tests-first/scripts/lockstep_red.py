"""pytest plugin: record, per test, the criteria it names and why it failed.

Loaded by red_report.py with ``-p lockstep_red``; writes JSON to $LOCKSTEP_RED_REPORT at the end of the run.
A red test must fail on an assertion or NotImplementedError, not because it cannot import or call the code.
"""

from __future__ import annotations

import json
import os

import pytest

EXPECTED = {"AssertionError", "NotImplementedError"}
WRONG = {"ImportError", "ModuleNotFoundError", "SyntaxError", "NameError", "AttributeError", "TypeError"}

_tests: dict[str, dict] = {}


def _criteria(item) -> list[str]:
    return [str(arg) for mark in item.iter_markers("ac") for arg in mark.args]


def _one_line(name: str, exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{name}: {text.splitlines()[0]}" if text else name


def pytest_collection_modifyitems(items):
    for item in items:
        _tests[item.nodeid] = {"acs": _criteria(item), "result": "not-run", "detail": ""}


def pytest_collectreport(report):
    if report.failed:
        detail = str(report.longrepr).strip().splitlines()[-1] if report.longrepr else ""
        _tests[report.nodeid or "<collection>"] = {"acs": [], "result": "collection-error", "detail": detail}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    entry = _tests.setdefault(item.nodeid, {"acs": _criteria(item), "result": "not-run", "detail": ""})
    if rep.skipped:
        entry["result"], entry["detail"] = "skipped", "xfail" if hasattr(rep, "wasxfail") else "skip"
    elif rep.when == "call" and rep.passed:
        entry["result"] = "passes"
    elif rep.failed and call.excinfo is not None:
        name = call.excinfo.typename
        entry["detail"] = _one_line(name, call.excinfo.value)
        if rep.when != "call":
            entry["result"] = "wrong-reason"  # a fixture or setup broke before the test body ran
        elif name in EXPECTED:
            entry["result"] = "red"
        elif name in WRONG:
            entry["result"] = "wrong-reason"
        else:
            entry["result"] = "check"


def pytest_sessionfinish(session):
    path = os.environ.get("LOCKSTEP_RED_REPORT")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_tests, f, indent=2)
