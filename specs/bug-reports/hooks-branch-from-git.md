# The hooks take the branch from CI variables, so an agent inside CI isn't protected

## Expected
The hooks judge the branch git has checked out. With a checkout on `main` and the CI variables naming
`feature/0099-other` (`GITHUB_HEAD_REF`, or Azure's `SYSTEM_PULLREQUEST_SOURCEBRANCH`), as in a CI job where an agent
runs, `git reset --hard HEAD~1` is blocked. With a checkout on `feature/0042-churn`, whose spec is tests-locked, an
edit to an existing test is blocked.

## Actual
Both are allowed. guard_bash sees the reset as running on `feature/0099-other`; protect_tests says "no spec for
branch 'feature/0099-other'; test edits are not locked here".

## Criterion
none

## Root cause
`core/src/lockstep_checks/spec.py`, `current_branch()`: it returns the CI variables' PR branch before asking git,
which is right for the checks (in a PR build HEAD is a detached merge commit) but not for the hooks, which judge the
checkout an agent works in. `hooks/guard_bash.py`, `hooks/protect_tests.py` and the event log in `hooks/__init__.py`
all call it without `env`. Found by the automated security review of the v0.5.1 upgrade on 2026-10-28; older than
this session (0.4.0 has it).

## Regression test
`core/tests/test_hooks_branch_from_git.py`. Before the fix:

```
FAILED test_guard_bash_blocks_a_rewrite_of_a_main_checkout_whatever_ci_says[ci_env0] - AssertionError: assert False
FAILED test_guard_bash_blocks_a_rewrite_of_a_main_checkout_whatever_ci_says[ci_env1] - AssertionError: assert False
FAILED test_protect_tests_judges_the_checked_out_spec_whatever_ci_says[ci_env0] - AssertionError: ("no spec for branch 'feature/0099-other'; test edits are not locked here (CI still checks them)",)
FAILED test_protect_tests_judges_the_checked_out_spec_whatever_ci_says[ci_env1] - (the same)
4 failed
```

## Why the tests missed it
The hook tests clear the CI variables first (`no_ci_env` in `conftest.py`, `no_pipeline_env` in `test_hooks.py`), so
they always ran as on a laptop.
