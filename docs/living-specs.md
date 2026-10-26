# Living specs

A Lockstep spec describes one change: what the work adds or replaces, reviewed before anything is built. After ten
changes to the same area, nobody can read off what the system does *now* without opening ten specs and following the
`superseded by` pointers. A living spec answers that question.

The idea comes from SDTRD, which keeps one canonical spec per capability in `specs/living/` and overwrites it with
the feature's full copy when the feature merges. Lockstep generates the living spec from the specs instead, so:

- **Test ids don't change.** Tests keep naming criteria by their spec (`0042/AC-001`); the living spec lists them
  under those names.
- **Nothing to keep in sync by hand.** `check_living_specs` regenerates the files and fails a PR that leaves them
  stale.
- **History stays.** The dated specs keep the why and the review trail; the living spec is the summary.

## Turn it on

```toml
[specs]
living = true
```

Then every spec past `draft` names its capability in `status.yml`:

```yaml
capability: churn-scoring
```

A capability is an area of behaviour the business would name: churn scoring, invoice matching, the refund assistant.
Pick it in the spec PR; `new_spec.py --capability churn-scoring` sets it.

## What the file holds

`specs/living/<capability>.md`, generated:

- **In force:** the active criteria of every `tests-locked` or `implemented` spec that names the capability. Since
  0.2.0 a spec reaches main as `tests-locked` only together with its green code (the test PR merges into the feature
  branch), so on main this is what the code does.
- **Coming:** the active criteria of `approved` specs: merged, tests not written yet. A reviewer sees what is about to
  change.

A struck criterion (`~~AC-003~~ superseded by 0057/AC-001`) drops out, and its replacement appears under its own
spec. Drafts are left out. Given/When/Then steps are kept under their criterion.

## Keep it current

```bash
PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_living_specs --write
```

Run it after changing a spec or its status, and commit the result in the same PR: the `spec` skill does this in the
spec PR, the `tests-first` skill in the test PR, where the status becomes `tests-locked`. In CI the check fails (or
warns, in warn mode) on:

- a living spec that is missing or out of date,
- a generated living spec whose capability no spec names any more (`--write` deletes it),
- a spec past `draft` without a capability.

`--write` never overwrites a file in `specs/living/` it didn't generate; a hand-written `README.md` there is safe.

## Later

If the team wants SDTRD's model, with the living spec as the source and feature specs as full copies, this is the
step towards it: the living files exist, and the folder layout matches. That change would move tests to capability
ids, so it is one to settle together with SDTRD's conventions.
