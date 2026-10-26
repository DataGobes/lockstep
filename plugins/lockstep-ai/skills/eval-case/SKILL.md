---
name: eval-case
description: Add LLM regression cases to a Lockstep repo's golden eval dataset, from an acceptance criterion, a bug or a production trace, with synthetic content only and a criterion reference, then register them in the MLflow evaluation dataset in Unity Catalog through code. Use when someone wants an eval case, a regression test for a prompt or LLM bug, to grow the golden set, or to turn a bad trace into a test.
---

# Add eval cases

Eval cases are tests: once a spec is tests-locked they are protected, so adding or changing them is a
`[test-change]` PR of its own, never mixed with the prompt or code it tests.

Paths below are relative to this skill's folder. `scripts/check_cases.py` needs Python 3.11+ and the repo's
`.lockstep/`.

## 1. Know the source

Ask which of these the case comes from, and get the criterion it tests (`<spec>/AC-<n>`):
- **A criterion:** read it and its spec; the case checks the behaviour it states.
- **A bug:** the expected and the actual answer; the case fails on the bug.
- **A production trace:** read it only to understand the situation. **Never copy real user text, names, ids or
  numbers from a trace.** Write a new, invented input that triggers the same behaviour.

If the source involves personal data and you are Claude, stop and say this goes to the company Copilot.

## 2. Write the cases

Add rows to the dataset under `evals/datasets/` (one JSON object per line, or the CSV the repo already uses), in the
MLflow GenAI shape with Lockstep's fields:

```json
{"id": "0042-ac001-late-order", "ac": "0042/AC-001",
 "inputs": {"question": "Where is order 1001? It was due yesterday."},
 "expectations": {"expected_facts": ["the new delivery date", "an apology"]}}
```

- Invented content only: "Test Person 001", order 1001, `@example.com` addresses.
- One behaviour per case; add the edge cases the criterion implies (empty input, ambiguity, a refusal it must make).
- Expectations a scorer can check: expected facts, an expected response, or guideline text for a judge.

## 3. Check them

```
python3 scripts/check_cases.py --root <repo> evals/datasets/<file>
```

It fails on a missing or unknown criterion, duplicate ids, empty inputs or expectations, and anything that looks like
real personal data (emails outside example domains, phone numbers, IBANs). Then run
`PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_ac_traceability` and the repo's eval command, and show the
user each new case's score: a regression case for an open bug should fail now.

## 4. Register the dataset in code

The Unity Catalog evaluation dataset is defined in code, not edited by hand. Add the new rows through the repo's
dataset definition (for example a module that calls `mlflow.genai.datasets.create_dataset` / `merge_records` with the
rows from `evals/datasets/`). Never upload from a notebook. Thresholds stay in `evals/thresholds.yml`; don't lower
them here.

## 5. Open the PR

Commit only the dataset rows and the dataset definition, as `<KEY> Add eval cases for <id>/AC-<n>`. The PR title
starts with `[test-change]` and the Jira key, and its description lists each case, its criterion and its current
score. Ask before pushing.
