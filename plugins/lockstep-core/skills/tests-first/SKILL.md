---
name: tests-first
description: Turn an approved Lockstep spec into failing tests, one or more per acceptance criterion, prove each fails for the right reason, and open the test PR into the feature branch that locks them. Use when a spec's status is approved and someone wants to write the tests, start the red phase, "write tests for spec 0042", or lock the tests before implementation.
---

# Write the failing tests for a spec

The tests are the contract the implementation must meet, and after this PR merges they are locked. Write tests that
fail now because the behaviour is missing, and that will pass only when the criterion is really met.

Paths below are relative to this skill's folder. The scripts need Python 3.11+ and the repo's own pytest.

## 1. Check the spec

- Find the spec: from the branch name, or ask for its id. Read `specs/<id>-<slug>/spec.md` and `status.yml`.
- `status` must be `approved`. If it is `draft`, stop: the spec PR comes first.
- **If `pii: yes` and you are Claude, stop** and say this spec is worked on in the company Copilot.
- Red tests never go to main: the test PR merges into the spec's feature branch, and only the green implementation
  merges into main. From an up-to-date main, create `feature/<id>-<slug>` if it doesn't exist yet and push it
  unchanged (ask first), then work on a new branch `test/<id>-<slug>` from it. Never on main.

## 2. Plan the tests

First agree the **seams**: where each criterion is tested from, such as a public function, a dbt model's output or a
prompt's response, so the tests check behaviour and survive refactoring. One seam per criterion is usual. These
locked tests are acceptance tests; the implementation adds its own unit tests later, one slice at a time. If the
spec has a `design.md`, its section 5 already names the seams: use them, and raise any that no longer fit.

From section 5 of the spec (test and eval plan), list each criterion with its seam, test type and location. Include the
edge cases the criterion's WHEN / IF conditions imply: empty input, the boundary values, duplicates, a failing
upstream. A Given/When/Then criterion maps straight onto the test: GIVEN is the setup, WHEN the one call through the
seam, THEN and AND the assertions, with the criterion's values. Use business terms as `GLOSSARY.md` defines them. Show the list, and settle anything unclear in rounds as
[../spec/grilling.md](../spec/grilling.md) describes, before writing.

## 3. Write them

Name the criterion in every test, with the spec id:

| Test type | How |
|---|---|
| pytest | `@pytest.mark.ac("<id>/AC-001")` on the test function (register the marker in `pyproject.toml` if it isn't) |
| dbt unit test | `name: ac_<id>_001_<what>` in a `*.unit_tests.yml` file, with hand-written `given:` rows and `expect:` rows |
| dbt data test | `meta: {ac: <id>/AC-001}` on the test's config |
| eval case | an `ac` field or column with `<id>/AC-001` in the golden dataset row |

Rules:
- Assert the behaviour the criterion states, with concrete expected values. A test that only checks "no exception",
  asserts a constant, or mocks the code it tests can never catch a wrong implementation.
- Take every expected value from an independent source: a literal, a worked example, the spec. Never compute it with
  the code under test or a copy of its logic; such a test agrees with whatever the code does.
- Fixtures use invented values only, such as "Test Person 001". Never real names, emails or data.
- New code may be needed so the tests can import and call it. Add only **stubs**: the module, the function signature
  and `raise NotImplementedError`, so each test fails on the missing behaviour rather than on an import.
- Don't change existing tests. If one contradicts the spec, stop and tell the user: that is a `[test-change]` PR.

## 4. Prove they are red for the right reason

For pytest:

```
python3 scripts/red_report.py --root <repo> --spec <id> --pytest "<how the repo runs pytest, e.g. uv run pytest>"
```

It runs the tests and prints an AC → test → result table. Every criterion needs a test that is **red**: it fails on an
assertion or `NotImplementedError`. Fix every other row: **passes** (the test checks nothing new, or the behaviour
already exists; tell the user), **skipped**, **wrong-reason** (import, name, attribute or type error, or a broken
fixture), **collection-error**, **no test**, **unknown criterion**. A **check** row failed on another exception:
decide whether that exception is the behaviour under test.

For dbt unit tests and eval cases, run them (`dbt test --select test_type:unit,<models>`, the repo's eval command) and
confirm by hand that each fails on the expected rows or scores, not on a compile error or a missing model.

Then run `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_ac_traceability`: every criterion must be covered.

## 5. Lock and open the test PR

- Commit the tests and stubs as `<KEY> Add failing tests for spec <id>`.
- In a second commit, set `status: tests-locked` in `status.yml` and `locked_at_commit:` to the SHA of the first
  commit. The lock starts when a human approves and merges this PR into the feature branch.
- Ask before pushing. Open the PR from `test/<id>-<slug>` **into `feature/<id>-<slug>`, not main**. The title starts
  with the Jira key; the description has the AC → test → result table from step 4, with each failure reason, and says
  the PR is a **test PR**. Review fixes to the tests go on the test branch; they are allowed until it merges.

Tell the user what comes next: a reviewer checks that the tests match the criteria (the feature branch's path-based
required reviewer covers `tests/`). Merge it with a squash or a merge commit, not a rebase. After merge, any change to
these tests needs a `[test-change]` PR, and the implementation continues on `feature/<id>-<slug>`, which merges into
main only when everything is green.
