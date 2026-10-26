# Mutation testing, report only

Coverage says which lines the tests ran. It does not say whether the tests would notice if those lines were wrong.
Mutation testing checks that: it changes the code in small ways (`<` becomes `<=`, `+` becomes `-`, `True` becomes
`False`), reruns the tests, and counts how many of these *mutants* the tests catch. A mutant that survives is a bug
the tests would let through.

This matters more with agents writing code. Lockstep locks the acceptance tests before the implementation, so an agent
can't weaken them; the mutation score shows whether those tests were strong enough in the first place.

SDTRD treats every surviving mutant as a blocking defect and requires a 100% kill score. Lockstep takes the idea from
there and starts with a report: the score and the missed mutants show on every PR, and nothing blocks. Once a team
knows its numbers, it can decide on a bar.

## What runs

The `mutation` job in `azure-pipelines-pr.yml` uses [`core/pipelines/mutation-report.yml`](../core/pipelines/mutation-report.yml),
which runs `python -m lockstep_checks.mutation_report`:

1. Lists the Python files the PR changed under `sourceDir` (default `src`), leaving out `test_*.py` and `conftest.py`.
2. Runs [mutmut](https://github.com/boxed/mutmut) on those modules only, so a small PR stays a short run.
3. Prints the score (`mutation score 82%: 41 of 50 mutants caught (7 survived, 2 no tests)`) and annotates each missed
   mutant, up to 20, as a warning at its file and line, with the change that survived: `if x < lo: -> if x <= lo:`.

A mutant is *caught* when a test fails (killed) or the tests time out on it. It is *missed* when every test still
passes (survived) or no test runs that code at all (no tests). The step never fails the PR: an error in mutmut itself
shows as a warning too.

Run it locally the same way:

```bash
PYTHONPATH=.lockstep/src python3 -m lockstep_checks.mutation_report --mutmut "uv run --with mutmut==3.8.0 mutmut"
uv run --with mutmut==3.8.0 mutmut browse   # look at each surviving mutant
```

## Requirements

- **Linux or macOS.** mutmut forks, so it does not run on Windows; the Azure Pipelines job uses `ubuntu-latest`.
- **A `src/` layout** or a package folder at the root. mutmut copies the code to `mutants/` and names mutants after the
  module (`src/pkg/mod.py` → `pkg.mod`). Tests must import the package by name (`from pkg.mod import f`), not by a
  `sys.path` trick in `conftest.py`.
- Add `mutants/` to `.gitignore`.

Settings beyond the source folder, such as files mutmut should skip, go in `[tool.mutmut]` in `pyproject.toml`; see
the mutmut docs.

## Parameters

| Parameter | Default | |
|---|---|---|
| `sourceDir` | `src` | Folder whose modules are mutated |
| `scope` | `changed` | `all` mutates every module, for a nightly or weekly run; it can take a long time |
| `mutmutVersion` | `3.8.0` | Pinned, so a mutmut release can't change the score overnight |

## Acting on a missed mutant

For each one, in SDTRD's order:

1. **Add an assertion that catches it.** Usually the boundary case nobody wrote down; it may belong in the spec too.
2. **Delete the code**, if no behaviour depends on it (an unreachable branch, a defensive check that can't trigger).
3. **Rewrite equivalent mutants away**, when the mutant behaves exactly like the original (`i < n` vs `i != n` in an
   index loop): iterate instead of indexing, drop the redundant condition.

Don't add the mutant to a skip list to raise the score.

## Later

Report only is the first step. A minimum score per PR, through the same `warn`/`enforce` switch as the other gates
([enforcement modes](enforcement-modes.md)), is the obvious next one, once the pilot shows what scores are realistic.
