# guard_bash trusts any git subcommand before a history rewrite except six it names

## Expected
Before a history rewrite, only git subcommands that leave HEAD, branches and config alone are trusted: `status`,
`log`, `diff`, `show`, `fetch`, `add`. From a session in a feature worktree, `git pull && git reset --hard HEAD~1`,
`git branch -f main HEAD && git reset --hard HEAD~1`, `git co main && git reset --hard HEAD~1` (an alias) and
`git $SUB main && git reset --hard HEAD~1` are blocked with "rewrites history in a checkout lockstep can't work out".
`git fetch -q && git status && git add -A && git commit --amend --no-edit` stays allowed.

## Actual
All four are allowed. The fix for [guard-bash-unfollowed.md](guard-bash-unfollowed.md) made the shell side an
allowlist, but the git side stayed a denylist: every subcommand except `checkout`, `switch`, `config`, `worktree`,
`init` and `clone` was trusted, including `pull`, `merge`, `branch -f`, aliases and a subcommand in a variable.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`: `_MOVES_GIT` lists the subcommands not to trust, and
`_history_folders()` trusts every other one.

## Regression test
`core/tests/test_guard_bash_git_allowlist.py`. Before the fix:

```
FAILED test_other_git_subcommands_before_a_rewrite_are_not_trusted[git pull && git reset --hard HEAD~1]
FAILED test_other_git_subcommands_before_a_rewrite_are_not_trusted[git merge main && git rebase main]
FAILED test_other_git_subcommands_before_a_rewrite_are_not_trusted[git branch -f main HEAD && git reset --hard HEAD~1]
FAILED test_other_git_subcommands_before_a_rewrite_are_not_trusted[git co main && git reset --hard HEAD~1]
FAILED test_other_git_subcommands_before_a_rewrite_are_not_trusted[git $SUB main && git reset --hard HEAD~1]
5 failed, 1 passed
```

## Why the tests missed it
`test_only_cd_and_plain_git_before_a_rewrite_are_trusted` tried only subcommands on the denylist. Found by the
automated security review of the guard-bash-unfollowed fix on 2026-10-27, after it had merged.
