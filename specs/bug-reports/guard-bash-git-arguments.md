# guard_bash trusts a read-only git subcommand whatever its options run

## Expected
A git subcommand on the trusted list is trusted before a history rewrite only without options that run a command or
write a file. From a session in a feature worktree,
`git fetch --upload-pack='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1` and
`git diff --output=.git/HEAD && git reset --hard HEAD~1` are blocked. A rewrite counts as such only when it is git's
own subcommand: `git fetch --upload-pack='git -C ../app reset --hard HEAD~1' .` is blocked, since the rewrite inside
the argument runs somewhere the fetch's folder says nothing about.

## Actual
All are allowed. The fix for [guard-bash-git-allowlist.md](guard-bash-git-allowlist.md) checks the subcommand
(`fetch`, `diff`) but not its options: `--upload-pack` / `-u` run a command, `--output` writes a file, and
`--ext-diff` / `--textconv` run configured programs. And a segment counts as a rewrite whenever the rewrite pattern
matches its text, so a rewrite inside an argument is judged by the outer command's folder.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`, `_history_folders()`: it trusts a segment by its subcommand alone, and
treats a segment as a rewrite from `_HISTORY.search(segment)` without checking that the rewrite is the subcommand
`_git_command()` parsed.

## Regression test
`core/tests/test_guard_bash_git_arguments.py`. Before the fix:

```
FAILED test_options_that_run_commands_or_write_are_not_trusted[git fetch --upload-pack='git checkout --ignore-other-worktrees main' . && git reset --hard HEAD~1]
... (the same for -u, --output, --ext-diff and --textconv)
FAILED test_a_rewrite_inside_another_git_commands_argument_is_blocked
6 failed
```

## The fix
A second review found the first version's option denylist incomplete: git takes any unambiguous prefix of a long
option (`--upload-p`) and bundles short ones (`-qu`), and a fetch refspec with a destination (`main:feature/x`),
with or without `--update-head-ok`, writes a branch. So a trusted subcommand now stays trusted only when its options
are all on a short list (`-q`, `-s`, `-b`, `--short`, `--stat`, `--oneline`, `--cached`, `-A`, `-p`, `-<n>` and a few
more) and, for `fetch`, no argument has a `:`. `test_only_listed_options_are_trusted` and
`test_listed_options_stay_trusted` pin both sides.

Out of reach for this hook: a single command that moves `main` without a history-rewriting subcommand
(`git fetch . +x:main`, `git branch -f main x`, `git update-ref`), and programs the repo's own config runs
(`diff.external`, filters). guard_bash recognises rewrites by their subcommand; the PR pipeline and branch policies
stay the gate for those.

## Why the tests missed it
The trusted-list tests used each subcommand with harmless options only. Found by the automated security review of
the guard-bash-git-allowlist fix on 2026-10-27.
