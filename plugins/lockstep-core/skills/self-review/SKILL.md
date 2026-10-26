---
name: self-review
description: Review a Lockstep feature branch before its PR opens, in two separate passes, standards (repo rules, changed tests, invented APIs, error masking) and spec (each criterion met, missing or wrong, quoted by AC id, plus scope creep), then fill in the PR description. Use at the end of the implement skill, or when someone asks to self-review or check a diff against its spec.
---

# Self-review before the PR

Review the branch the way the human reviewer will, and fix what you find before they have to. The review has two
passes that answer different questions: does the code follow the rules (**standards**), and does it do what the spec
says (**spec**). Keep the two reports separate and never merge or re-rank them, so a clean pass on one can't hide a
problem on the other. Report honestly: a finding you fix is fine; a finding you hide reaches the reviewer anyway.

Paths below are relative to this skill's folder. `scripts/review_diff.py` needs Python 3.11+, git and the repo's
`.lockstep/`.

## 1. Gather the facts

```
python3 scripts/review_diff.py --root <repo> --spec <id> --python "<the repo's python, e.g. uv run python>"
```

It lists the changed files, existing protected files that changed, added lines that may mask errors, new imports that
don't resolve in the repo's environment, and the spec's criteria with their text. Both passes start from this output.

## 2. Run the two passes

In Claude, run each pass as its own subagent, in parallel, each given the output of step 1 and only the files it
names. In Copilot, run them one after the other in a fresh chat each, so the second isn't shaped by the first.

### Standards pass

Input: the diff, `AGENTS.md` (its review rules block wins over anything below) and the repo's conventions.

1. **Changed tests.** "Existing protected files changed" must be empty. If not, undo those changes; a real test change
   is a `[test-change]` PR. New tests are fine.
2. **Invented APIs.** Every unresolved import or missing name is a bug until proven otherwise. Check it against the
   pinned version (`uv.lock`, `requirements*.txt`) and its docs.
3. **Error masking.** For each flagged line, decide whether it hides a failure. A broad `except` that continues, or
   `coalesce` / `try_cast` that turns bad input into a plausible value, needs a reason and a test, or it goes.
4. **Special-casing.** The code must not branch on fixture values, detect a test run or hard-code expected outputs.
5. **Tautological tests.** A new test's expected value must come from an independent source (a literal, a worked
   example, the spec), never from the code under test.
6. **Smells, as judgement calls.** Duplicated logic (reuse the existing helper, macro or model), a long function doing
   several things, a name that doesn't say what it holds, dead code, a magic number the spec names. Label each one a
   judgement call; a repo rule that says otherwise wins.

### Spec pass

Input: the diff, `specs/<id>-<slug>/spec.md` and the criteria list from step 1. Ignore style.

For **each criterion**, quote it by id and give one verdict with the evidence (file and line, test name):
- **met**: the code does what the criterion says, including its WHEN / IF condition and its values.
- **missing**: nothing in the diff does it.
- **wrong**: the code does something else, or only passes the test without meeting the words.

Then **scope**: for each changed file, the criterion that needs it. A file no criterion needs, or anything section 2
lists as out of scope, is scope creep: revert it or move it to its own PR. The same goes for code inside a needed file that no
criterion uses yet: a helper, an abstraction, a config flag or a new dependency.

## 3. Fix, then report

Fix what you can, rerun the checks from the implement skill, and run step 1 and both passes again. A **missing** or
**wrong** verdict you can't fix without changing a locked test goes to the user, not into the code.

## 4. Fill in the PR description

Use the repo's `.azuredevops/pull_request_template.md`:

- **AC → test → result:** run
  `python3 ../tests-first/scripts/red_report.py --root <repo> --spec <id> --expect green --pytest "<repo's pytest>"`
  and paste its table; add rows for dbt and eval tests by hand.
- **Self-review:** the two reports, under their own headings, with what you fixed.
- **Assumptions:** every decision you made that the spec doesn't state.
- **Agent used** and **PR type: implementation**; tick only the checklist items that are true.

Then tell the user what you found and fixed, what is left for the reviewer to judge, and ask before pushing.
