---
name: baseline
description: Pin behaviour that existing code already has in a Lockstep baseline spec, with characterisation tests that pass today, so a repo with existing code can join Lockstep without speccing everything first. Use when someone wants to adopt Lockstep in an existing codebase, "baseline" or "pin" an area, write characterisation tests, find out what some legacy code does before changing it, or asks where to start in a brownfield repo.
---

# Pin existing behaviour with a baseline spec

A change spec describes new behaviour and its tests start red. A baseline spec describes what the code does today and
its tests pass from the start. It changes no code. Once it merges, its tests are protected like any other, and a later
change spec that alters the behaviour supersedes the criterion. The flow is in docs/baseline-specs.md.

Paths below are relative to this skill's folder. The scripts need Python 3.11+ and git.

## 0. Is it a baseline?

Route it elsewhere when the user wants new or different behaviour (`/spec`) or a fix for wrong behaviour (`bugfix`).
A baseline only records what is there. A behaviour that looks wrong becomes a bug report or an open question, never
a criterion.

## 1. Check the repo

- It needs `specs/_template/baseline/` and `.lockstep/`. If they are missing, stop and offer `bootstrap-repo`.
- The working tree must be clean. If it isn't, ask first.
- Ask for the Jira key (optional when `[jira] required = false`), the track, and whether the area touches personal
  data. **If PII is yes and you are Claude, stop** and say this continues in the company Copilot.

## 2. Choose the area

Run `git fetch origin`, then `python3 scripts/hotspots.py --root <repo>`. It ranks folders by commits over the last
year and says which are already pinned. Recommend the area the user's next change touches; failing that, the busiest
unpinned one. Keep it to what three to ten criteria can cover: one module, model group or endpoint. Let the user decide.

## 3. Create the spec

```
python3 ../spec/scripts/new_spec.py --root <repo> --baseline --title "<area> as it works today" --track <track> --pii no --jira <KEY>
```

It writes `status.yml` with `kind: baseline` and prints the branch name. Create `baseline/<id>-<slug>` from an
up-to-date main.

## 4. Find out what the code does

Read the code, its existing tests, its callers and any docs. List each behaviour a caller relies on: outputs for
normal input, edge cases (empty, duplicate, late, invalid), errors raised, side effects. For each, note where you saw
it (`path:line`). Run the code on small invented inputs where reading is not enough. Then sort the list:

- **intended:** becomes a criterion;
- **looks wrong:** a bug report later, through `bugfix`; leave it out of the criteria and name it in section 2;
- **unclear:** an open question.

Settle the unclear ones with the author in rounds, as [../spec/grilling.md](../spec/grilling.md) describes.

## 5. Write the spec

Fill all seven sections of `spec.md`, keeping the headings. Criteria use the repo's `[specs] ac_format`, state
today's behaviour with concrete values, and carry an `Observed in:` line. Name pinned paths in section 2: that marks
the area as pinned for `hotspots.py`. Run `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_ac_traceability
--spec-only` and fix every error. Set `status: approved` once section 7 is empty and the user agrees with the list.

## 6. Pin each criterion with a passing test

- **Adopt an existing test** that already checks a criterion: add only the tag line (`@pytest.mark.ac("<id>/AC-001")`,
  `meta: {ac: <id>/AC-001}`, `import pytest` if needed). Change nothing else in the file: on a `baseline/` branch,
  `check_test_tamper` allows tag-only additions and nothing more.
- **Write a new test** in a new file for every other criterion, through the seam a caller uses. Expected values are
  literals: run the code once, write the result down, and check it says what the criterion says. If they disagree,
  stop: the criterion or the code is wrong, and that goes back to the author.
- Fixtures use invented values only. Freeze clocks and stub external services so the tests stay deterministic.

Run `python3 ../tests-first/scripts/red_report.py --root <repo> --spec <id> --expect green --pytest "<pytest command>"`:
every criterion needs a passing test. For dbt and eval tests, run them and confirm they pass. Then run
`check_ac_traceability` without `--spec-only`.

## 7. Lock and open the PR

- Commit the tests as `<KEY> Pin <area> with tests`.
- In a second commit, set `status: implemented` and `locked_at_commit:` to the first commit's SHA. With living specs
  on, run `check_living_specs --write` and add `specs/living/` to it. Set the status last: from then on the hooks
  treat existing tests as locked.
- Ask before pushing. Open the PR from `baseline/<id>-<slug>` into main. The title starts with the Jira key; in the PR
  template choose **PR type: baseline**. The pipeline's Lockstep summary comment shows each criterion with its green
  test; don't paste a table.

Tell the user what comes next: a reviewer checks that each criterion is behaviour worth keeping. After merge, a change
spec that alters it strikes the criterion (`~~AC-002~~ superseded by 0057/AC-001`), and a person updates its test in
a `[test-change]` PR (docs/baseline-specs.md).
