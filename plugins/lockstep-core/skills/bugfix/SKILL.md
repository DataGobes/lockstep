---
name: bugfix
description: Fix a bug in a Lockstep repo through the light lane, a bug report, a new regression test shown red, then the smallest fix, all in one bugfix/ PR, instead of a full spec. Use when someone reports a bug, says "fix MXAAI-123", or a check, test or user finds wrong behaviour that an existing criterion or the code's obvious intent already covers.
---

# Fix a bug through the light lane

A bug is behaviour that is already meant to work. It doesn't need a new spec, only proof: a report that says what's
wrong, a test that fails because of it, and the smallest change that makes it pass. All three go in one PR on a
`bugfix/` branch, and `check_spec_required` fails that PR if the report or the new test is missing. The lane follows
SDTRD's Fast-Track Protocol (Gates B1 to B3).

## 0. Is it a bug?

Stop and route it elsewhere when:
- the fix needs behaviour that no criterion or obvious intent describes: that is new work, so run `/spec`;
- the fix needs an existing locked test to change: that is a `[test-change]` PR first, reviewed on its own;
- the spec it touches has `pii: yes`: continue in the company Copilot.

Dependency bumps, config and tooling with no behaviour change aren't bugs either: use a `chore/<slug>` branch.

## 1. Branch

From an up-to-date main: `git switch -c bugfix/<KEY>-<slug> origin/main`, with the Jira key, for example
`bugfix/MXAAI-123-null-prices`. Use `hotfix/` instead only when the team's release process names it.

## 2. Write the bug report (B1)

Copy `specs/bug-reports/_template.md` to `specs/bug-reports/<KEY>-<slug>.md` and fill in every section. Expected and
Actual need a small example with invented values. Criterion names the broken criterion by id (`0042/AC-003`) or says
`none`. Leave Root cause as a guess until step 3 confirms it.

## 3. Prove it with a red regression test (B2)

Add a **new** test file; existing test files stay locked. Name the criterion when there is one
(`@pytest.mark.ac("0042/AC-003")`, `ac_0042_003_<what>` for a dbt unit test) so traceability links it. The expected
value comes from the report's Expected section, never from running the code.

Run it and confirm it fails **for the bug's reason**: the assertion shows the wrong value from Actual, not an import
error or a typo. Paste the failure into the report. Commit the report and the test together, `<KEY> Reproduce <what>`,
before touching the code, so the history shows red before green.

## 4. Fix it (B3)

Make the smallest change that turns the test green: no refactor, no extra features. Then run the implement skill's
step 4 loop: the full suite, lint, format, types, `dbt build` on changed models, and the Lockstep checks including
`spec_required`. Commit as `<KEY> Fix <what>`. Update Root cause if the fix proved the guess wrong.

## 5. Review and open the PR

Run the self-review skill's standards pass; for its spec pass, check the fix against the report's Expected and the
named criterion. In the PR template choose **PR type: bugfix**, link the report, and paste the red failure and the
green run. Ask before pushing.
