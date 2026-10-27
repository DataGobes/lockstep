# guard_bash judges history rewrites by the session's folder, not the folder the command runs in

## Expected
The "rewrites history on main" rule looks at the branch checked out where the git command runs. With a checkout
`app/` on `main` and a worktree `app-0042/` on `feature/0042-x`:

- from a session in `app/`, `cd ../app-0042 && git commit --amend -m x` is allowed (it amends `feature/0042-x`);
- from a session in `app-0042/`, `cd ../app && git reset --hard HEAD~1` is blocked (it rewrites `main`);
- the same with `git -C <folder> ...` instead of `cd`.

## Actual
The rule reads the branch of the session's own folder (`event.cwd`) and ignores a `cd` or `-C` in the command, so
both cases above come out the wrong way round: the amend on the feature branch is blocked as "rewrites history on
main", and the hard reset of `main` is allowed. The first happened in this repo on 2026-10-27, when an amend in the
spec 0003 worktree was blocked because the main checkout was on `main`.

## Criterion
none

## Root cause
`core/src/lockstep_checks/hooks/guard_bash.py`, `hook()`: it calls `current_branch(repo_root(event.cwd))` once for the
whole command, so the folder a `cd` or `git -C` moves to never reaches the branch check.

## Regression test
`core/tests/test_guard_bash_cd.py`. Before the fix:

```
FAILED core/tests/test_guard_bash_cd.py::test_cd_into_a_feature_worktree_allows_amend - AssertionError: BLOCKED by lockstep: this command rewrites history on main; work on a feature branch
FAILED core/tests/test_guard_bash_cd.py::test_cd_into_main_blocks_reset - assert False
FAILED core/tests/test_guard_bash_cd.py::test_git_dash_c_into_main_blocks_rebase - assert False
FAILED core/tests/test_guard_bash_cd.py::test_git_dash_c_into_a_feature_worktree_allows_amend - AssertionError: BLOCKED by lockstep: this command rewrites history on main; work on a feature branch
```

A security review of the first fix found that trusting every `cd` opened a bypass the old rule didn't have: in
`(cd ../app-0042 && git log); git reset --hard HEAD~1`, the `cd` stays in the subshell and the reset runs on `main`.
A second review found that checking the session's folder as well isn't enough: from a feature worktree, that folder
isn't on `main`, so `cd -P ../app && git reset --hard ...` or `git -c core.worktree=../app reset --hard ...` still got
through. The fix therefore blocks any history rewrite whose folder it can't follow, from any branch. It follows only a
plain `cd <folder> &&` or `cd <folder>;` to a folder that exists, and a segment that starts with `git` whose only
options before the subcommand are `-C`. Anything else counts as not followed: a subshell, braces or command
substitution; a pipe or `||` after a `cd`; `cd` with options or an unknown target; `pushd`/`popd`; `GIT_DIR`,
`GIT_WORK_TREE` or `GIT_COMMON_DIR`; `--git-dir` or `--work-tree`; `-c`; or git started by another command
(`bash -c`, `xargs`). The two parametrized tests in the regression file cover these, from a session on `main` and from
one on a feature branch.

Still open, and older than this fix: an earlier command in the same line that switches the target checkout to `main`
(`git checkout main && git reset --hard ...` from a feature branch) is judged by the branch before the switch.

## Why the tests missed it
`test_history_rewrite_blocked_only_on_main` runs every command from the repo's own folder; no test moved to another
checkout first. Worktrees became the normal way to implement a spec (the implement skill) after the rule was written.
