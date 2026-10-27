# <KEY>: <short title>

Copy this file to `specs/bug-reports/<KEY>-<slug>.md`, for example `MXAAI-123-null-prices.md`. Use invented values only.

## Expected
What should happen, with a small example input and the output it should give.

## Actual
What happens instead, for the same input. Paste the error or the wrong output.

## Criterion
The acceptance criterion this breaks, such as `0042/AC-003`, or `none` when no spec covers this code yet.
If the fix needs behaviour that no criterion describes, this is not a bug: write a spec instead.

## Root cause
Why it happens, in one or two sentences, naming the file and function.

## Regression test
The new test file, and the failure it gave before the fix (the assertion, not just "failed").

## Why the tests missed it
Which test should have caught it, or why none existed. This feeds the next retro.
