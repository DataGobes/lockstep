# implement

**What it does.** Builds a `tests-locked` spec in its own worktree and feature branch, one vertical slice at a time,
until the locked tests and every check are green. If a locked test looks wrong, it stops and explains instead of
changing it.

**When to reach for it.** After the test PR merges into the spec's feature branch. Say "implement spec 0042".

**Common questions.**
- *Can several agents work on one spec at once?* Yes, when its slices are independent. After the shared contracts are
  committed, `scripts/streams.py add <stream> ...` gives each stream its own worktree and branch, an agent works in
  each, and each comes back through a PR into the feature branch. The locked tests stay locked in every stream. The
  protocol follows SDTRD's parallel worktrees.
- *It refused to start.* The message says why: the test PR hasn't merged into the feature branch, the spec is PII,
  or another worktree already implements it.
- *Can it add tests?* Yes, unit tests as it goes. Only the locked acceptance tests can't change.

**It's working if** implementation PRs need no `[test-change]` follow-ups and no "where's the test?" comments.
