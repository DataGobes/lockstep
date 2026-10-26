# tests-first

**What it does.** Writes failing acceptance tests for an approved spec, one seam per criterion, and proves each fails
because the behaviour is missing, not because of an import error. Then it opens the test PR that locks them.

**When to reach for it.** When a spec is `approved`. Say "write the tests for spec 0042".

**Common questions.**
- *Isn't writing all tests first an anti-pattern?* Only the acceptance tests are written first; the implementation
  still works in small red-green slices. See [why tests first](../why-tests-first.md).
- *What does "wrong-reason" mean in the table?* The test fails before it reaches the behaviour: fix the test or stub.

**It's working if** every criterion has a red row, and the test PR review is about the criteria, not the test code.
