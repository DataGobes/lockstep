# guard_bash misses abbreviated and bundled git options before a history rewrite

## Expected
Before a history rewrite, a read-only git command stays trusted only when all its options are on a short list. From
a session in a feature worktree,
`git fetch --upload-p='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1`,
`git fetch -qu '...' . && git reset --hard HEAD~1`, `git diff --out=.git/HEAD && git reset --hard HEAD~1` and
`git fetch --update-head-ok . main:feature/0042-x && git reset --hard HEAD~1` are blocked.
`git status -sb && git diff --cached --name-only && git log --oneline -5 && git fetch -q origin main` before a rewrite
stays allowed.

## Actual
All four are allowed. The fix for [guard-bash-git-arguments.md](guard-bash-git-arguments.md) rejects exact option
names (`--upload-pack`, `-u`, `--output`, `--ext-diff`, `--textconv`), but git also takes any unambiguous prefix of a
long option and bundles short ones. A fetch refspec with a destination writes a branch, and with `--update-head-ok`
the checked-out one.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`, `_history_folders()`: `_RUNS_OR_WRITES` and the `-u` check deny
spellings of options instead of allowing a known set.

## Regression test
`core/tests/test_guard_bash_git_options.py`. Before the fix:

```
FAILED test_only_listed_options_are_trusted[git fetch --upload-p='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1]
FAILED test_only_listed_options_are_trusted[git fetch -qu 'git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1]
FAILED test_only_listed_options_are_trusted[git diff --out=.git/HEAD && git reset --hard HEAD~1]
FAILED test_only_listed_options_are_trusted[git log --ext -p && git reset --hard HEAD~1]
FAILED test_only_listed_options_are_trusted[git fetch --update-head-ok . main:feature/0042-x && git reset --hard HEAD~1]
5 failed, 1 passed
```

## Out of reach
A single command that moves `main` without a history-rewriting subcommand (`git fetch . +x:main`,
`git branch -f main x`, `git update-ref`), and programs the repo's own config runs (`diff.external`, filters).
guard_bash recognises rewrites by their subcommand; the PR pipeline and branch policies stay the gate for those.

## Why the tests missed it
The option tests used each option's full name only. Found by the automated security reviews of the
guard-bash-git-arguments fix on 2026-10-27; the fix reached that PR's branch after it had merged.
