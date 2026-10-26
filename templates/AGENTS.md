# Agent instructions for <repo name>

<One or two sentences: what this repo builds, for whom, and its main parts.>
Track: <data | ai | mixed>. Work follows Lockstep: spec first, tests locked, small PRs.

## How work flows

1. A Jira issue sets the track and the PII flag.
2. **Spec PR:** `specs/<id>-<slug>/spec.md` with numbered acceptance criteria (AC-001, ...). Nothing is built before it is approved.
3. **Test PR:** failing tests that name their criterion, then `status.yml` becomes `tests-locked`.
4. **Implementation PR** on `feature/<id>-<slug>`, until every check is green.
5. Copilot reviews first, then a human who did not drive the agent approves.

## Non-negotiables

Hooks and the PR pipeline enforce these. Do not try to work around them.

1. **Tests are locked.** Once the spec is `tests-locked`, do not modify, delete, skip or weaken an existing test, fixture,
   snapshot, dbt unit-test YAML, eval dataset or threshold. Adding new tests is fine. A real test change is a separate
   PR whose title starts with `[test-change]`.
2. **Stop rather than cheat.** If a test looks wrong, stop and explain why. Never special-case inputs, detect a test run
   or hard-code expected values to make a test pass.
3. **PII goes to Copilot.** If the spec has `pii: yes`, stop and tell the user to continue in the company Copilot.
4. **No production data.** Read code, schemas and synthetic fixtures only. Fixtures use invented values such as
   "Test Person 001", never real names, emails or phone numbers.
5. **No prod from an agent.** Deploy to `dev` only. Prod deploys run from main through an approved Azure DevOps environment.
6. **Contracts are versioned, not edited.** A dbt model with `contract: enforced` changes only through a new model
   version that a spec describes.
7. **Small batches.** Aim for 400 changed lines or fewer per PR, and never more than 100 files.

Business terms mean what `GLOSSARY.md` says. Use its terms in specs, tests and code, not the synonyms it lists to avoid.

## Naming the criterion a test covers

Use the spec id, because every spec numbers from AC-001:

- pytest: `@pytest.mark.ac("0042/AC-001")`
- dbt unit test: `name: ac_0042_001_<what>` in a `*.unit_tests.yml` file
- dbt data test: `meta: {ac: 0042/AC-001}`
- eval case: an `ac` field or column with `0042/AC-001`

## Commands

<!-- Filled in for this repo by the bootstrap-repo skill. Keep only the ones that exist. -->
- Tests: `<uv run pytest>`
- Lint and format: `<uv run ruff check . && uv run ruff format --check .>`
- Types: `<uv run pyright>`
- dbt (changed models only): `<dbt build --select state:modified+ --defer --state <path>>`
- Bundle: `<databricks bundle validate -t dev>`
- Evals: `<command>`
- Lockstep checks: `PYTHONPATH=.lockstep/src python -m lockstep_checks.check_<name>` (pr_size, jira_key, test_tamper,
  ac_traceability, review_rules)

## Definition of done for an agent task

- All tests and checks are green locally.
- No existing test file changed. New tests are allowed.
- The PR description has the AC → test → result table filled in.
- Assumptions you made are listed in the PR description.

<!-- lockstep:review-rules -->
## Lockstep review rules

- Flag a new test that does not name its criterion: `@pytest.mark.ac("<spec>/AC-<n>")`, a dbt unit test named `ac_<spec>_<n>_...`, or `meta: {ac: <spec>/AC-<n>}`.
- Flag a test that cannot fail: it only checks that no exception is raised, asserts a constant, compares a value with itself, or mocks the code it tests.
- Flag a test whose expected value is computed by the code under test or a copy of its logic; expected values come from a literal, a worked example or the spec.
- Flag implementation code that branches on literal values from test fixtures, or on signs of a test run such as `PYTEST_CURRENT_TEST` or an environment named `test`.
- In a PR whose title starts with `[test-change]`, flag loosened assertions, wider tolerances, lower eval thresholds and removed expected rows, and ask which criterion justifies each one.
- Flag scope creep: refactors, renames or formatting changes in files the change does not need, mixed into a feature or fix.
- Flag a changed column, type or constraint in a dbt model with `contract: enforced`; it needs a new model version instead.
- Flag log lines, print statements and exception messages that include row values or person-related columns (names, emails, addresses, phone numbers); log ids and counts instead.
- Flag error masking: a broad `except` that continues, or `coalesce` / `try_cast` that hides bad input without a test that covers it.
- Flag fixtures, seeds and examples with realistic personal data; use invented values such as "Test Person 001".
<!-- /lockstep:review-rules -->

## About this repo

<!-- Repo-specific notes: layout, boundaries, gotchas. Keep the whole file under 150 lines. -->
