# Property tests for invariant criteria

Read this when a criterion states a rule that holds for **every** input, not one worked example. Example tests check
the cases someone thought of; a property test lets Hypothesis generate hundreds of inputs and shrinks any failure to
the smallest one. The idea comes from Kiro, which derives property tests from its EARS requirements.

## Which criteria

Look for words that quantify over all inputs: *always*, *every*, *any*, *never*, *no row*, *for all*, and the plain
EARS form `THE <system> SHALL ...` without a trigger. Typical properties in data work:

| Criterion says | Property |
|---|---|
| totals are never negative | `assert result >= 0` for any valid input |
| deduplication keeps one row per key | output keys are unique, and every input key appears |
| the transform is safe to rerun | `f(f(x)) == f(x)` (idempotent) |
| export then import gives the same data | `load(dump(x)) == x` (round trip) |
| sorting keeps all rows | same multiset of rows before and after |
| a filter only removes rows | output is a subset of the input |

A criterion with one concrete example (GIVEN 600 EUR, THEN waits) stays an example test. Add a property test next to
the example tests; never replace them: the examples document the behaviour, the property guards the edges.

## How

- Only if the repo already pins `hypothesis`. If it doesn't, ask the user before adding it: it is a new dependency.
- Name the criterion like any test: `@pytest.mark.ac("<id>/AC-003")` on the test function.
- Generate only valid inputs as the criterion defines them (strategies with `min_value`, `alphabet`, `unique_by`), so
  a failure is about the behaviour, not about input the system rejects anyway.
- Locked tests must not be flaky. Use `@settings(derandomize=True, max_examples=200, deadline=None)` so CI and every
  laptop run the same examples. Write the cases Hypothesis finds as extra `@example(...)` lines, so they stay
  pinned.
- Expected outcomes come from the criterion, never from the code under test: assert the property, not a value you
  computed with the implementation.

```python
from hypothesis import example, given, settings, strategies as st

amounts = st.decimals(min_value=0, max_value=10_000, places=2)

@pytest.mark.ac("0042/AC-003")
@settings(derandomize=True, max_examples=200, deadline=None)
@given(st.lists(amounts, max_size=50))
@example([])
def test_total_is_never_negative(lines):
    assert order_total(lines) >= 0
```

With a stub that raises `NotImplementedError`, the property test is red for the right reason, and `red_report.py`
shows it like any other test.
