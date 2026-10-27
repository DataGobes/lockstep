# guard_bash allows a history rewrite on main from a feature worktree when it can't follow the cd

## Expected
A history rewrite whose checkout guard_bash can't work out is blocked, whatever branch the session is on. With `app/`
on `main` and the worktree `app-0042/` on `feature/0042-x`, from a session in `app-0042/`, each of these is blocked:
`cd -P ../app && git reset --hard HEAD~1`, `if true; then cd ../app; fi && git reset --hard HEAD~1`,
`git -c core.worktree=../app reset --hard HEAD~1`, `bash -c 'git -C ../app reset --hard HEAD~1'`.
A plain `git rebase -i HEAD~1` or `git commit --amend` in `app-0042/` stays allowed.

## Actual
All four are allowed. The fix for [guard-bash-cd.md](guard-bash-cd.md) follows plain `cd` and `git -C`, and when it
can't follow a folder change it checks the session's folder as well. That only blocks when the session itself is on
`main`; from a feature worktree, the session's folder says nothing about where the command lands.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`, `_history_folders()`: a folder change it can't follow adds the
session's folder to the folders to check instead of blocking. It also misses folder changes it doesn't recognise as
such: a `cd` that isn't the first word of its segment (`then cd`, `command cd`, `eval`, `source`), `GIT_CONFIG_*`
variables, `$CDPATH`, `~`, and `..` after a symlink, which the shell resolves logically and the hook physically.

## Regression test
`core/tests/test_guard_bash_unfollowed.py`. Before the fix:

```
FAILED test_a_rewrite_whose_checkout_it_cannot_work_out_is_blocked_from_a_feature_branch[cd -P ../app && git reset --hard HEAD~1]
... (the same for each of the 11 cases)
FAILED test_cd_with_cdpath_set_is_not_followed
FAILED test_cd_resolves_dot_dot_before_symlinks_like_the_shell
13 failed, 1 passed
```

## Why the tests missed it
`test_guard_bash_cd.py` tries every folder change it can't follow from a session on `main` only. Found by two automated
security reviews of the guard-bash-cd fix on 2026-10-27; the second round's commit reached that PR's branch after it
had merged.
