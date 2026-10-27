# Review rules for this repository

<!-- lockstep:review-rules: copied from AGENTS.md by `python -m lockstep_checks.check_review_rules --write`. Edit AGENTS.md, not this block. -->
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
