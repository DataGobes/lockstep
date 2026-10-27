# Glossary

Business terms this repo uses, so specs, tests and code mean the same thing. The spec and tests-first skills read it
and add to it. One entry per term, in alphabetical order. Use invented examples only.

## Acceptance criterion

**Means:** one numbered, testable statement in a spec (AC-001, AC-002, ...) that a test names with
`@pytest.mark.ac("<spec>/AC-<n>")`; every spec numbers from AC-001.
**Avoid:** "requirement", "user story", "AC" without the spec id.
**Where:** `core/src/lockstep_checks/specdoc.py` parses them; `check_ac_traceability` holds tests to them.

## Baseline

**Means:** a spec with `kind: baseline` that describes what existing code does today, pinned by tests that pass now,
in a PR that changes no code.
**Avoid:** "characterisation spec", "legacy spec", "snapshot".
**Where:** `plugins/lockstep-core/skills/baseline/`, `docs/baseline-specs.md`.

## Lane

**Means:** the branch prefix that decides what a PR needs: `feature/`, `test/`, `spec/` and `baseline/` need a spec;
`bugfix/` and `hotfix/` need a bug report and a regression test; `chore/` needs neither.
**Avoid:** "workflow", "flow", "branch type".
**Where:** `[lanes]` in `lockstep.toml`; `core/src/lockstep_checks/check_spec_required.py`.

## Spec

**Means:** the folder `specs/<id>-<slug>/` with `spec.md` (criteria, non-goals, test plan) and `status.yml`
(lifecycle, track, PII flag, lock commit); the only thing an agent builds from.
**Avoid:** "ticket", "design doc", "PRD".
**Where:** `templates/specs/_template/`, `core/src/lockstep_checks/spec.py`.

## Tests-locked

**Means:** the spec status after its test PR merged: the tests exist, failed for the right reason, and existing tests
may no longer change outside a `[test-change]` PR. `locked_at_commit` records the commit.
**Avoid:** "frozen", "approved tests", "red phase done".
**Where:** `core/src/lockstep_checks/lock.py`, `check_test_tamper`, the `protect_tests` hook.

## Track

**Means:** which kind of work a spec is (`data`, `ai` or `mixed`), set in `status.yml`; it picks the test conventions
and the PR jobs that apply. Not the same as a lane.
**Avoid:** "stream", "domain", and "lane" for this.
**Where:** `tracks` in `lockstep.toml`; `core/src/lockstep_checks/status.py`.
