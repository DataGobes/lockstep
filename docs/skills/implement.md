# implement

**What it does.** Builds a `tests-locked` spec in its own worktree and feature branch, one vertical slice at a time,
until the locked tests and every check are green. If a locked test looks wrong, it stops and explains instead of
changing it.

**When to reach for it.** After the test PR merges. Say "implement spec 0042".

**Common questions.**
- *It refused to start.* The message says why: the test PR hasn't merged, the spec is PII, or another branch already
  implements it.
- *Can it add tests?* Yes, unit tests as it goes. Only the locked acceptance tests can't change.

**It's working if** implementation PRs need no `[test-change]` follow-ups and no "where's the test?" comments.
