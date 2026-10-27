# Agent instructions for Lockstep

Lockstep is a set of Claude Code and GitHub Copilot CLI plugins for spec-first, test-locked development with coding
agents: the skills (`plugins/`), the shared checks and hooks they rely on (`core/`), the files bootstrap copies into a
product repo (`templates/`) and release tooling (`tools/`). This repo builds itself the Lockstep way.
Track: mixed. Work follows Lockstep: spec first, tests locked, small PRs.

## How work flows

1. A Jira issue sets the track and the PII flag.
2. **Spec:** `specs/<id>-<slug>/spec.md` with numbered acceptance criteria (AC-001, ...). Nothing is built before it is approved.
3. **Spec and test PR** from `test/<id>-<slug>` into `feature/<id>-<slug>`, never into main: the spec, and failing
   tests that name their criterion, then `status.yml` becomes `tests-locked`. The tests are locked once it merges.
   A large or risky spec (`[specs]` in `lockstep.toml`) gets a spec PR of its own into main first, from
   `spec/<id>-<slug>`; the test PR then holds only the tests.
4. **Implementation** on `feature/<id>-<slug>` until every check is green; its last commit sets `status.yml` to
   `implemented`. Only then does it merge into main, so main never holds a failing test.
5. Copilot reviews first, then a human who did not drive the agent approves.

Two lighter lanes skip the spec. **Bugfix** (`bugfix/<KEY>-<slug>`): a bug report in `specs/bug-reports/`, a new
regression test shown red, then the smallest fix, in one PR. **Chore** (`chore/<slug>`): dependency bumps, config and
tooling that change no behaviour. The PR pipeline fails any other code change without a spec.

Existing code without a spec gets a **baseline** first (`baseline/<id>-<slug>`): a spec with `kind: baseline` that
describes what the code does today, and tests that pass today. The PR changes no code; it may tag existing tests
with a criterion but not otherwise edit them.

## Non-negotiables

Hooks and the PR pipeline enforce these. Do not try to work around them. A "would block (warn mode)" message
means the same as a block: stop and say why.

1. **Tests are locked.** Once the spec is `tests-locked`, do not modify, delete, skip or weaken an existing test, fixture,
   snapshot, dbt unit-test YAML, eval dataset or threshold. Adding new tests is fine. A real test change is a separate
   PR whose title starts with `[test-change]`, from `test/<id>-<slug>-<what>` into the spec's feature branch while it
   is being built, or into main once it is implemented; for a test no spec names, from `chore/<what>`.
2. **Stop rather than cheat.** If a test looks wrong, stop and explain why. Never special-case inputs, detect a test run
   or hard-code expected values to make a test pass.
3. **PII goes to Copilot.** If the spec has `pii: yes`, stop and tell the user to continue in the company Copilot.
4. **No production data.** Read code, schemas and synthetic fixtures only. Fixtures use invented values such as
   "Test Person 001", never real names, emails or phone numbers.
5. **No prod from an agent.** Deploy to `dev` only. Prod deploys run from main through an approved Azure DevOps environment.
6. **Contracts are versioned, not edited.** A dbt model with `contract: enforced` changes only through a new model
   version that a spec describes.
7. **Small batches.** Aim for 400 changed lines or fewer per PR, and never more than 100 files.
8. **Build only what a criterion needs.** No helpers, abstractions, config flags or extension points that no
   criterion uses yet; no new dependency where the standard library or a pinned one does. Code no criterion needs is
   dead code: delete it. (After SDTRD's YAGNI rules.)

Business terms mean what `GLOSSARY.md` says. Use its terms in specs, tests and code, not the synonyms it lists to avoid.

## Naming the criterion a test covers

Use the spec id, because every spec numbers from AC-001:

- pytest: `@pytest.mark.ac("0042/AC-001")`
- dbt unit test: `name: ac_0042_001_<what>` in a `*.unit_tests.yml` file
- dbt data test: `meta: {ac: 0042/AC-001}`
- eval case: an `ac` field or column with `0042/AC-001`

## Commands

Plain `pip` and `python -m`, as `.github/workflows/ci.yml` runs them; there is no root `pyproject.toml` or `uv.lock`.

- Tests: `python -m pytest -q core/tests plugins/lockstep-core plugins/lockstep-data plugins/lockstep-ai tools/tests`
- Lint and format: `ruff check core && ruff format --check core`, then the same with `--line-length 120` on
  `plugins/lockstep-* tools`
- Plugin validation: `npx --yes @anthropic-ai/claude-code plugin validate --strict .` (and each `plugins/*/`)
- Release metadata: `python tools/check_release.py`
- Lockstep checks: `PYTHONPATH=.lockstep/src python -m lockstep_checks.check_<name>` (pr_size, jira_key, spec_required,
  test_tamper, ac_traceability, review_rules, living_specs, team_rules)

## Definition of done for an agent task

- All tests and checks are green locally.
- No existing test file changed. New tests are allowed.
- The Lockstep summary comment on the PR is clean, or the description says why a line in it is not.
- Assumptions you made are listed in the PR description.

<!-- lockstep:review-rules -->
## Lockstep review rules

- Flag a new test that does not name its criterion: `@pytest.mark.ac("<spec>/AC-<n>")`, a dbt unit test named `ac_<spec>_<n>_...`, or `meta: {ac: <spec>/AC-<n>}`.
- Never offer a code suggestion that edits a test file the spec's `status.yml` has locked (one that existed at `locked_at_commit`), not even to add a criterion tag: accepting it breaks the lock. Comment instead that the change needs a `[test-change]` PR.
- Flag a test that cannot fail: it only checks that no exception is raised, asserts a constant, compares a value with itself, or mocks the code it tests.
- Flag a test whose expected value is computed by the code under test or a copy of its logic; expected values come from a literal, a worked example or the spec.
- Flag implementation code that branches on literal values from test fixtures, or on signs of a test run such as `PYTEST_CURRENT_TEST` or an environment named `test`.
- In a PR whose title starts with `[test-change]`, flag loosened assertions, wider tolerances, lower eval thresholds and removed expected rows, and ask which criterion justifies each one.
- Flag scope creep: refactors, renames or formatting changes in files the change does not need, and speculative code no criterion uses (unused helpers, abstractions, config flags, new dependencies), mixed into a feature or fix.
- Flag a changed column, type or constraint in a dbt model with `contract: enforced`; it needs a new model version instead.
- Flag log lines, print statements and exception messages that include row values or person-related columns (names, emails, addresses, phone numbers); log ids and counts instead.
- Flag error masking: a broad `except` that continues, or `coalesce` / `try_cast` that hides bad input without a test that covers it.
- Flag fixtures, seeds and examples with realistic personal data; use invented values such as "Test Person 001".
<!-- /lockstep:review-rules -->

## About this repo

- `core/` is the source of `lockstep-checks`; `.lockstep/` is the copy bootstrap vendored into this repo, pinned to the
  tag in `.lockstep/VERSION`. Change `core/`, never `.lockstep/`; after a release, run `/bootstrap-repo` with the new
  tag to upgrade the copy.
- Tests live next to what they test: `core/tests/`, `plugins/<plugin>/skills/<skill>/tests/`, `tools/tests/`. The
  `[protect]` globs in `lockstep.toml` cover those paths.
- GitHub (`origin`) is home: PRs go there, need no Jira key, and CI runs on GitHub Actions (`.github/workflows/ci.yml`).
  `azure-pipelines-pr.yml` is this repo's own PR pipeline for an Azure DevOps mirror, where Lockstep is tried out the
  way a product repo uses it; `azure-pipelines-deploy.yml` there is the unused template.
- A release is a CHANGELOG section, `python3 tools/check_release.py --set-version <version>`, a merge, then the tag
  `v<version>` on the merge commit.
