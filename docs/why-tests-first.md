# Why Lockstep writes the tests first

A fair critique of test-first agent workflows says: writing all the tests before any code is *horizontal slicing*.
You design the whole test suite against an imagined implementation, the tests end up coupled to that imagined
design, and when the real code needs a different shape the tests fight it. Good TDD instead moves in thin *vertical
slices*: one failing test, the code to pass it, refactor, repeat.

We agree with the critique, and Lockstep is built so it doesn't apply.

## What is locked, and what isn't

Lockstep locks **acceptance tests**, not the whole test suite.

- **One seam per criterion.** Each acceptance criterion (`0042/AC-001`) gets a test at an agreed seam: a public
  function, a dbt model's output, a prompt's response. The tests-first skill agrees the seams before writing any test.
  A seam is behaviour someone outside the code relies on, so it survives refactoring.
- **Inside, vertical slices.** The implement skill works red-green one slice at a time, and adds its own unit tests
  freely. Only the locked acceptance tests are off limits.

So the locked tests say *what* must be true, in the words of the spec. The code and the unit tests under them are
free to take whatever shape the work needs.

## Why lock them at all

With a person writing code, test-first is a design aid. With an agent writing code, it is also a **control**:

- An agent that may edit the tests can make any change "pass", and will under pressure. Locked tests, a hook that
  blocks edits to them, and a CI check that fails on changed tests remove that option.
- The test PR is reviewed by a person before any code exists, so the reviewer checks the tests against the spec on
  their own, not against code that already looks plausible.
- The test PR merges into the spec's feature branch, not main, so main never holds a failing test (Mohammed's rule,
  from SDTRD). The lock is the commit where it merged: the history proves the tests came first, and the hook and CI
  protect the tests from that commit on.
- Every test names its criterion, so the PR shows criterion → test → result, and a missing criterion is visible.

## When a locked test is wrong

It happens: the spec was ambiguous, or the seam was wrong. The agent stops and explains instead of bending the test,
and a person opens a `[test-change]` PR that names the criterion and is reviewed like any other change. That is
slower than editing the test in place, on purpose.
