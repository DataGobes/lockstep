# tests-first

**What it does.** Writes failing acceptance tests for an approved spec, one seam per criterion, and proves each fails
because the behaviour is missing, not because of an import error. Then it opens the test PR that locks them. That PR merges into the spec's feature branch, never into main, so main
never holds a failing test. Criteria that hold for every input ("never negative", "one row per key") also get a Hypothesis property test next to
the example tests, when the repo uses Hypothesis.

**When to reach for it.** When a spec is `approved`. Say "write the tests for spec 0042".

**Common questions.**
- *Isn't writing all tests first an anti-pattern?* Only the acceptance tests are written first; the implementation
  still works in small red-green slices. See [why tests first](../why-tests-first.md).
- *What does "wrong-reason" mean in the table?* The test fails before it reaches the behaviour: fix the test or stub.

- *Why not into main?* Failing tests on main would make main red until the code lands. On the feature branch the
  commit order still proves the tests came first, and main only gets the green result. This follows Mohammed's rule
  from SDTRD: no broken code on main.

**It's working if** every criterion has a red row, and the test PR review is about the criteria, not the test code.
