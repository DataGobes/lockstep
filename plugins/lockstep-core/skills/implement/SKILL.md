---
name: implement
description: Implement a Lockstep spec against its locked tests, in its own git worktree and feature branch, looping on the tests and checks until green, and stopping rather than bending code or tests when a test looks wrong. Use when a spec is tests-locked and someone wants to build it, "implement spec 0042", "make the tests pass", or start the green phase.
---

# Implement a spec against its locked tests

The tests were reviewed and locked before you start. Your job is code that meets the criteria, so the tests pass
because the behaviour is right, never because the code knows what the tests check.

Paths below are relative to this skill's folder. `scripts/start_implement.py` needs Python 3.11+ and git.

## 1. Start the work

```
python3 scripts/start_implement.py --root <repo> --spec <id>
```

It refuses, with the reason, unless the spec on origin/main is `tests-locked` (the test PR merged), is not
`pii: yes`, and has no other branch or worktree (one implementation per spec at a time). Then it creates a worktree
next to the repo, `../<repo>-<id>`, on `feature/<id>-<slug>`. Work only in that worktree from here on.

If it refuses because of PII and you are Claude, stop and say the spec is implemented in the company Copilot.

## 2. Plan briefly

Read the spec (all seven sections) and every test that names one of its criteria. Write a short plan for the user: the
files you will create or change, mapped to criteria, and anything in section 2 (non-goals) you must not touch.
Mention any criterion whose test you don't understand before writing code.

## 3. Implement one slice at a time

The locked tests are acceptance tests, one or more per criterion at the seams the test PR agreed. Inside them, work in
vertical slices: pick one criterion, write a small unit test for the next piece of behaviour it needs, make it pass,
then the next. Never write all the code first and test after. New unit tests are always allowed; only the locked
tests are off limits.

- One slice per commit, message `<KEY> <what>` (the Jira key from status.yml). A slice is done when its new tests and
  the criterion's locked tests that it covers pass.
- Replace the stubs from the test PR with the real behaviour. Keep to the spec's scope; no drive-by refactors.
- Follow AGENTS.md and the repo's own conventions. Use only libraries the repo already pins, unless the spec says
  otherwise; check a function exists in the pinned version before calling it.
- Fixtures and examples use invented values only.

## 4. Loop until green

Run, in this order, and fix what fails:
1. The spec's tests, which must all pass:
   `python3 ../tests-first/scripts/red_report.py --root . --spec <id> --expect green --pytest "<repo's pytest>"`
2. The repo's full test suite, lint, format and type checks (the commands in AGENTS.md).
3. For dbt work: `dbt build` on the changed models and their children (see AGENTS.md).
4. The Lockstep checks: `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_<name>` for `spec_required`,
   `test_tamper`, `ac_traceability`, `pr_size` and `review_rules`.

The hooks stay on. A hook block is information, not an obstacle: never look for another way to make the same change.

## 5. When a test looks wrong, stop

If a test seems to contradict the spec, test the wrong thing, or need a value the spec doesn't give, **stop**. Don't
change the test, skip it, or special-case its inputs in the code (branching on fixture values, detecting a test run,
hard-coding the expected output). Write down which test, what it expects, what the spec says, and why they disagree,
and give that to the user. A real test fix is a separate `[test-change]` PR that a reviewer approves.

## 6. Finish

When everything is green, run the `self-review` skill. It checks the diff against the spec and fills in the PR
description. Then ask before pushing and opening the PR.
