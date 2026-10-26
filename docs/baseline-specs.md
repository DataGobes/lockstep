# Baseline specs: joining Lockstep with existing code

Lockstep's main flow assumes new behaviour: a spec, tests that fail, then code that makes them pass. Most repos that
adopt it already have code that nobody wrote a spec for. A **baseline spec** covers that code: it describes what an
area does today and pins it with tests that pass today. It changes no code.

The idea comes from three tools in the October 2026 landscape scan: OpenSpec (specs for brownfield code), BMAD
("verified context on a codebase you inherited") and Agent OS (standards found in the existing code). The tests are
what Michael Feathers calls characterisation tests.

## When to write one

- **Before changing an area** that has no spec. Pin what it does, then write the change spec against it. The
  baseline makes the change's effect visible: the criteria it supersedes are exactly the behaviour that changes.
- **When an area breaks often** or nobody is sure what it does.
- **Not for everything at once.** Start with the areas that change most. `hotspots.py` in the `baseline` skill ranks
  folders by commits over the last year and shows which are pinned already.

## How it differs from a change spec

| | Change spec | Baseline spec |
|---|---|---|
| `status.yml` | `kind: change` (or no `kind`) | `kind: baseline` |
| Lifecycle | draft → approved → tests-locked → implemented | draft → approved → implemented |
| Tests | fail first (red), then the code makes them pass | pass from the start (characterisation tests) |
| Branches | `spec/`, `test/` into `feature/`, `feature/` into main | one PR from `baseline/<id>-<slug>` into main |
| Code changes | yes, on `feature/` | none: tests, specs and docs only |
| Existing tests | locked | may be adopted by adding a criterion tag only |

Everything else is the same: the seven spec sections, the criterion formats, the open-questions rule, traceability,
living specs and superseding.

## The baseline PR

`check_spec_required` holds a `baseline/<id>-` branch to three rules:

1. The spec has `kind: baseline`.
2. The PR changes only tests (`[protect] globs`), specs and docs. Any other file fails: it belongs in a feature,
   bugfix or chore PR.
3. If it changes tests, the spec is `implemented` by the end of the PR, with `locked_at_commit` set to the commit
   that added them. `check_ac_traceability` then requires a test for every criterion.

`check_test_tamper` allows one more thing on a `baseline/` branch: an existing test file may gain criterion tags, as
long as the change only adds tag lines (`@pytest.mark.ac("0042/AC-001")`, `pytestmark = pytest.mark.ac(...)`,
`meta: {ac: 0042/AC-001}`, `import pytest`, blank lines) and removes nothing. Any other edit to an existing test
fails as usual.

A baseline spec cannot be `tests-locked`, and its id cannot be used on a `feature/` or `test/` branch: new behaviour
gets its own change spec.

## When a change spec alters pinned behaviour

1. In the change spec's spec PR, strike the baseline criterion and point to its replacement:
   `- ~~AC-002~~ superseded by 0057/AC-001`. `check_ac_traceability` checks that the pointer resolves.
2. The test that pins the old behaviour fails once the new behaviour is built. Agents cannot edit it (it existed
   before the change spec was tests-locked), so a person updates or removes it on the feature branch, in a commit of
   its own.
3. Title the feature PR into main `[test-change] <KEY> ...`. The tamper check reports the test change as a warning,
   and the required reviewer approves it knowingly.

## Upgrading a repo

`branch_pattern` in lockstep.toml must match `baseline/`. The default does from 0.4; a repo that sets its own pattern
adds `baseline` to it (`check_spec_required` says so when it doesn't). Run `/bootstrap-repo` to get the baseline spec
template in `specs/_template/baseline/`.
