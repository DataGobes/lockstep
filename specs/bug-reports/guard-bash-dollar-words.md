# guard_bash trusts a git option it can only see after the shell expands it

## Expected
Before a history rewrite, a git command with a word containing `$` isn't trusted. From a session in a feature
worktree, `git fetch $'--upload-pack=git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1` and
`git fetch $OPT . && git reset --hard HEAD~1` are blocked. A `$` in the rewrite's own arguments, as in
`git commit --amend -m "$MSG"`, stays allowed.

## Actual
Both are allowed. `shlex` doesn't know bash's `$'...'` and `$"..."` quoting, so the word reaches the option check as
`$--upload-pack=...`, which doesn't start with `-`; bash runs it as `--upload-pack=...`. A variable such as `$OPT`
can hold any option.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`, `_history_folders()`: the option allowlist from
[guard-bash-git-options.md](guard-bash-git-options.md) looks only at words that start with `-` after `shlex`, so a
word the shell turns into an option later is never checked.

## Regression test
`core/tests/test_guard_bash_dollar_words.py`. Before the fix:

```
FAILED test_a_word_with_a_dollar_before_a_rewrite_is_not_trusted[git fetch $'--upload-pack=git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1]
FAILED test_a_word_with_a_dollar_before_a_rewrite_is_not_trusted[git fetch $OPT . && git reset --hard HEAD~1]
FAILED test_a_word_with_a_dollar_before_a_rewrite_is_not_trusted[git log $"--output=.git/HEAD" && git reset --hard HEAD~1]
3 failed, 1 passed
```

## Why the tests missed it
The option tests wrote every option literally. Found by the automated security review of the v0.5.2 upgrade (#63) on
2026-10-28.
