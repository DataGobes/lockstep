# Demo: Lockstep on an SDTRD repo

`demo.py` builds an SDTRD project with SDTRD's own `sdtrd init` and templates, adds Lockstep with the
[SDTRD profile](../../templates/sdtrd/lockstep.toml), and runs the checks on five PRs, as the GitHub Actions workflow
would. Nothing goes into the project's `specs/` beyond what SDTRD itself writes: Lockstep reads the gate boxes.

```sh
python examples/sdtrd-demo/demo.py                 # clones SDTRD at the commit the profile was built against
python examples/sdtrd-demo/demo.py --sdtrd ../SDTRD --keep /tmp/sdtrd-demo   # use a checkout, keep the projects
```

It exits 1 if a PR gets a different verdict than expected. See [Lockstep on an SDTRD repo](../../docs/sdtrd.md).

## What it shows

| PR | What happens | Verdict |
|---|---|---|
| 1 | Code on `feat/w1.1-token-check` with Gate 2 ticked but Gate 4 open | blocked by `spec_required`: tick Gate 4 in tasks.md |
| 2 | Into main with Gate 4 ticked, REQ-AUTH-2 untested, Gate 6 open | blocked by `spec_required` (Gate 6) and `ac_traceability` (REQ-AUTH-2 has no test) |
| 3 | The feature is done, but a shipped test was loosened to make it pass | blocked by `test_tamper` |
| 4 | `fix/` PR whose bug report has Gate B1 open | blocked by `spec_required` |
| 5 | Gates 2, 4 and 6 ticked, both requirements tagged in Gherkin (`@REQ-AUTH-1`, `@REQ-AUTH-2`) | passes |

SDTRD's spec-to-code audit lets PRs 1 to 4 through, since each changes something under `specs/`; these checks add
the gate-level detail on top of it.

## Output

```text
PR 1: feat/w1.1-token-check -> main  [BLOCKED]
  Code before the tasks are approved: Gate 2 ticked, Gate 4 not.
  FAIL  spec_required
        ERROR check_spec_required: specs/features/w1.1-token-check/specs/tokens/spec.md: spec w1.1 is approved; a feature PR that changes code needs it tests-locked or implemented (tick Gate 4 in tasks.md)
  ok    ac_traceability
  ok    test_tamper
  ok    pr_size
  ok    team_rules

PR 2: feat/w1.1-token-check -> main  [BLOCKED]
  Into main with Gate 4 ticked, one requirement untested and Gate 6 not ticked.
  FAIL  spec_required
        ERROR check_spec_required: specs/features/w1.1-token-check/tasks.md: spec w1.1 is still tests-locked; as the last commit before the PR into main, tick Gate 6 in tasks.md, so once this merges the spec shows as done
  FAIL  ac_traceability
        ERROR check_ac_traceability: specs/features/w1.1-token-check/specs/tokens/spec.md:8: requirement REQ-AUTH-2 has no test (name it in a test, e.g. @REQ-AUTH-2)
  ok    test_tamper
  ok    pr_size
  ok    team_rules

PR 3: feat/w1.1-token-check -> main  [BLOCKED]
  Same feature, but the agent loosened a shipped test to make its change pass.
  ok    spec_required
  ok    ac_traceability
  FAIL  test_tamper
        ERROR check_test_tamper: tests/test_parse.py: modifies an existing test or eval file
        ERROR check_test_tamper: If a test is wrong, stop and explain why. A real test change goes in its own PR titled '[test-change] ...'.
  ok    pr_size
  ok    team_rules

PR 4: fix/empty-token-crash -> main  [BLOCKED]
  A bug fix whose report is not triaged yet (Gate B1 open).
  FAIL  spec_required
        ERROR check_spec_required: specs/bug-reports/2026-10-27-empty-token-crash.md: the bug report's Gate B1 (triage and root cause) is not ticked; code waits for it
  ok    ac_traceability
  ok    test_tamper
  ok    pr_size
  ok    team_rules

PR 5: feat/w1.1-token-check -> main  [PASSES]
  The feature done the SDTRD way: gates 2, 4 and 6 ticked, every requirement tested.
  ok    spec_required
  ok    ac_traceability
  ok    test_tamper
  ok    pr_size
  ok    team_rules

```
