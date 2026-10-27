# protect_tests lets a locked test through when the base branch doesn't have it yet

## Expected
A test that existed at an `implemented` spec's `locked_at_commit` is locked on every branch. With `origin/main`
lacking `tests/test_b.py`, and spec 0042 `implemented` with `locked_at_commit` at the commit that added it, an edit to
`tests/test_b.py` on `test/0042-churn-sync` is blocked: "tests/test_b.py existed before spec 0042 was tests-locked".

## Actual
The edit is allowed silently, without even a warning. In this repo on 2026-10-27, `sed -i` on
`core/tests/test_config_baseline.py` (baseline 0002, `implemented`, `locked_at_commit: 3ab8aa9`) went through on the
branch that merged Azure DevOps `main` into GitHub `main`. `origin/main` was GitHub's, which didn't have the file yet.
The change itself was an approved `[test-change]`, but the hook should have flagged it.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/protect_tests.py`, `_check()`: a file counts as locked only if it exists on the base
branch or at the lock commit `lock.lock_commit()` finds. That search runs only on `feature/` branches and follows
first parents, so on a `test/` branch, or with the lock on a merge's second parent, it finds nothing. The
`locked_at_commit` in `status.yml` was never consulted, although that commit was in the local repo.

## Regression test
`core/tests/test_protect_tests_locked_at_commit.py`. Before the fix:

```
E       AssertionError: ()
E       assert False
E        +  where False = Decision(block=False, message='', warnings=()).block
FAILED core/tests/test_protect_tests_locked_at_commit.py::test_test_at_an_implemented_specs_locked_at_commit_is_locked
```

`test_tests_in_an_open_test_pr_stay_editable` passed before and after: a `tests-locked` spec on its own `test/` branch
keeps its tests editable during review, so the fallback applies only once the spec is `implemented`.

## Why the tests missed it
Every protect_tests test builds `origin/main` from the same history as the branch, so the base always had the file.
Two remotes whose `main` branches had diverged, with work moving between them by merge, were never modelled.
