# Lockstep on an SDTRD repo

[SDTRD](https://github.com/mgabs/SDTRD) defines the workflow: gates 0 to 6, the feature, bugfix and chore lanes,
REQ-/NFR- keys, living specs. Lockstep can enforce that workflow in CI without changing how an SDTRD repo is laid out.
Nothing new goes into `specs/`: Lockstep reads the folders, keys and ticked Review Gate boxes SDTRD already uses.

## Set up

1. Copy the Lockstep core to `.lockstep/` (`/bootstrap-repo`, or copy `core/src` by hand).
2. Save [`templates/sdtrd/lockstep.toml`](../templates/sdtrd/lockstep.toml) as `lockstep.toml`.
3. Save [`templates/github-actions-pr.yml`](../templates/github-actions-pr.yml) as `.github/workflows/lockstep.yml`
   and delete the `jira_key`, `review_rules` and `living_specs` steps. It runs next to SDTRD's own rails workflow.
4. Start in warn mode (the profile's default). Switch a check to `enforce` once its numbers say it is right
   ([enforcement modes](enforcement-modes.md)).

## What each gate means to Lockstep

| SDTRD | Lockstep reads it as |
|---|---|
| Gate 2 ticked in every `specs/<capability>/spec.md` of the feature | approved |
| Gate 4 ticked in `tasks.md` | tests-locked: code may change on `feat/<id>-<slug>` |
| Gate 6 ticked in `tasks.md`, or the folder is in `specs/archive/` | implemented: the PR into main may merge |
| Gate B1 ticked in the bug report | a `fix/` PR may change code |

## What the checks add to SDTRD's rails

| Check | On an SDTRD repo |
|---|---|
| `check_spec_required` | Code on `feat/` needs Gate 4 ticked, and the PR into main needs Gate 6. A `fix/` PR needs a bug report in `specs/bug-reports/` with Gate B1 ticked and a new regression test. `chore/` needs nothing. SDTRD's own audit only asks that something under `specs/` changed. |
| `check_ac_traceability` | Every REQ-/NFR- key of a feature past Gate 4 is named by a test, and every key a test names exists. Keys in `specs/living/` without a test are warnings: they shipped before Lockstep. |
| `check_test_tamper` | An existing test file may not be changed, renamed, deleted, skipped or weakened, unless the PR title starts with `[test-change]`. |
| `check_pr_size`, `check_team_rules` | As in any Lockstep repo. |

## Linking a test to a requirement

SDTRD keys are unique across the repo, so a test names the key itself, anywhere in a test file:

```gherkin
@REQ-AUTH-1
Scenario: An empty token is rejected
```

```python
def test_empty_token_is_rejected():  # REQ-AUTH-1
```

A retired key stays in its spec marked `[DEPRECATED by <id>]`; a test that still names it gets a warning.

## Not used on SDTRD repos

- The Lockstep test lock: SDTRD commits each slice's red tests with its green code, so there is no lock commit.
  Existing tests on main are still protected.
- Jira keys, Copilot review rules, Lockstep living specs (SDTRD keeps its own), the red-evidence report.
- The trust summary comment, which is Azure DevOps only for now.
