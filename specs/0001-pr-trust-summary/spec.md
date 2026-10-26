---
id: 0001
title: PR trust summary
owner: DataGobes
reviewer: <engineer>
---

# PR trust summary

## 1. Problem and outcome
Lockstep already collects the evidence that makes agent-written code trustworthy: every criterion has a test, the tests
were locked before the code, nobody weakened them, and the mutation report says how strong they are. Today that
evidence is spread over pipeline logs, warnings on lines, build tags and a table the agent pastes into the PR
description. A reviewer has to dig for it, and the pasted table is the agent grading its own work.

Developers and reviewers need one short comment on every PR, computed by the pipeline, that answers "can I trust this
change?" at a glance and says what to do when the answer is no. If it works, reviewers read the comment instead of
re-deriving the evidence, approve agent PRs faster, and developers want Lockstep on their repo because it makes their
AI-written PRs easy to approve.

We will know it worked when, in the pilot:
- reviewers say they read the summary first (retro question), and
- median time from "PR opened" to "first approval" on agent PRs drops against the repo's pre-Lockstep baseline.

## 2. Scope / non-goals
- In scope: a `trust_summary` module in `lockstep-checks`; an evidence file written by each existing PR job (Lockstep
  checks, quality, mutation, dbt Slim CI); a final pipeline job that merges the evidence and posts or updates one comment
  on the Azure DevOps PR; the same summary locally as Markdown or JSON.
- In scope: PRs on every branch kind Lockstep knows (`spec/`, `test/`, `feature/`, `bugfix/`, `hotfix/`, `baseline/`,
  `chore/`), including the default spec-and-tests PR into a feature branch.
- Out of scope (agent must not touch): what any existing check passes or fails; the summary only reads their results.
- Out of scope: a single trust score or grade. Each signal is shown on its own, so nobody optimises a number.
- Out of scope: GitHub PR comments, Azure DevOps PR status badges, a dashboard across PRs. The JSON output is designed
  so these can follow without changing the producers.
- Out of scope: eval results for the ai track. Eval rows are listed as linked, with no result, until the eval gate
  writes an evidence file (open question 3).

## 3. Acceptance criteria (each testable)
- AC-001 WHEN a PR pipeline run finishes, whether its jobs passed or failed, THE SYSTEM SHALL post a Lockstep summary
  comment on the Azure DevOps PR.
- AC-002 WHEN the PR already has a Lockstep summary comment, THE SYSTEM SHALL replace that comment's text instead of
  adding another comment.
- AC-003 WHEN the summary comment is created, THE SYSTEM SHALL create its thread in the closed state, so that a branch
  policy requiring all comments to be resolved is never blocked by it.
- AC-004 WHEN every signal the run measured is clean, THE summary SHALL start with one line saying so, with the number
  of criteria that have a passing test.
- AC-005 WHEN at least one signal is not clean, THE summary SHALL start with each signal that is not clean, each with
  the next step that fixes it.
- AC-006 WHEN the branch has an active spec, THE summary SHALL list every criterion that is not superseded, with each
  test that names it and that test's result in this run: passed, failed, red as expected, red for the wrong reason,
  skipped, or not run.
- AC-007 WHEN the PR targets a feature branch, THE summary SHALL apply the tests-first red report's rules to the spec's
  new tests: a failure on an assertion or NotImplementedError is "red as expected" and clean; a pass, or a failure on
  any other error, is not clean.
- AC-008 WHEN the spec is tests-locked, THE summary SHALL show the commit where the tests were locked (short SHA and
  date) and whether any protected file that existed at that commit has changed since.
- AC-009 WHEN the test-tamper check ran, THE summary SHALL show its result, with each protected file a `[test-change]`
  PR changes listed as an approved test change rather than as clean.
- AC-010 WHEN the mutation job ran, THE summary SHALL show the mutation score and the number of missed mutants.
- AC-011 WHEN the changed-line coverage step ran, THE summary SHALL show the coverage of changed lines next to the
  repo's minimum.
- AC-012 IF a signal was not measured (its job was skipped, switched off, crashed, or left no evidence file), THEN THE
  summary SHALL show it as "not measured" with the reason, never as clean.
- AC-013 WHEN the branch is in a lane that needs no spec, THE summary SHALL name the lane in place of the criteria
  table.
- AC-014 WHEN the branch is a `bugfix/` or `hotfix/` branch, THE summary SHALL show the bug report and the result of
  its regression test.
- AC-015 THE SYSTEM SHALL build the summary only from evidence files written by this pipeline run, git history and the
  base branch's `lockstep.toml`, never from the PR description.
- AC-016 IF posting or updating the comment fails, THEN THE SYSTEM SHALL log a warning naming the cause and the
  permission to grant, publish the summary as a pipeline artifact, and finish the job as succeeded.
- AC-017 WHEN a developer runs `python -m lockstep_checks.trust_summary` locally, THE SYSTEM SHALL print the summary
  as Markdown from the evidence files in the working tree, identical to the comment the pipeline would post.
- AC-018 WHEN the summary command runs with `--json`, THE SYSTEM SHALL print the summary as JSON that carries a
  `schema_version`.
- AC-019 (non-functional) THE headline and signal lines SHALL take at most 8 lines, with the criteria table folded into
  a collapsed section above 10 rows.
- AC-020 (non-functional) THE summary job SHALL add at most 60 seconds to the pipeline's wall-clock time, measured on
  the pilot repo.

## 4. Interfaces and data contract
**Evidence files (the contract).** Each job that measures something writes `lockstep-evidence/<producer>.json` and
publishes it as a pipeline artifact. Producers do not know about the comment; the renderer does not know how a signal
was measured. A new signal (evals, data diff, safety scan) is a new producer and needs no change to the renderer.

```json
{
  "schema_version": 1,
  "producer": "quality",
  "status": "measured",            // measured | skipped | error
  "reason": null,                   // why, when not measured
  "signals": {
    "tests": [{"node": "tests/test_x.py::test_y", "acs": ["0042/AC-001"],
               "result": "passed", "detail": ""}],
    "coverage_changed_lines": {"percent": 86.0, "minimum": 80}
  }
}
```

Producers in this spec: `checks` (each Lockstep check's findings and mode, from `report.emit`), `lock` (lock commit
and protected files changed since, from `lock.py`), `quality` (pytest results per test with its `ac` markers, via the
pytest plugin the red report uses, moved into core; changed-line coverage), `mutation` (from
`mutation_report.summarize`), `dbt` (unit test results from `run_results.json`, linked to criteria by
`check_ac_traceability.find_test_refs`).

**Pipeline.** `core/pipelines/trust-summary.yml`, a job that `dependsOn` every other PR job and runs with
`condition: always()`. It downloads the evidence artifacts, renders, and posts. A product repo adds it with one line in
`azure-pipelines-pr.yml`, and `bootstrap-repo` adds it on upgrade.

**Azure DevOps.** Pull Request Threads REST API with `System.AccessToken`. The comment carries a hidden marker
(`<!-- lockstep-trust-summary -->`) so the job finds and updates its own thread. The project's build service needs
*Contribute to pull requests* on the repository; the branch-policy doc and `ado/branch-policy.sh` say so.

**Local.** `python -m lockstep_checks.trust_summary [--evidence lockstep-evidence] [--json]`. The JSON output is
versioned with `schema_version`; a later dashboard or PR status reads it.

**Versioning.** Evidence and output schemas start at 1. A renderer reads every schema version it knows and shows an
unknown producer or version as "not measured: unknown evidence format", never as clean.

## 5. Test and eval plan
Tests name criteria with this spec's id: `@pytest.mark.ac("0001/AC-001")`.

| AC | Test type | Location |
|----|-----------|----------|
| AC-001 | unit, fake ADO client: comment created after a passing and a failing run | core/tests/test_trust_summary_post.py |
| AC-002 | unit, fake ADO client: second run updates the same thread | core/tests/test_trust_summary_post.py |
| AC-003 | unit, fake ADO client: thread status on create | core/tests/test_trust_summary_post.py |
| AC-004 | unit, render from all-clean evidence fixtures | core/tests/test_trust_summary_render.py |
| AC-005 | unit, render with one and with two failing signals | core/tests/test_trust_summary_render.py |
| AC-006 | unit, render: criteria table, superseded criteria left out | core/tests/test_trust_summary_render.py |
| AC-007 | unit, render with a feature-branch target and red results of each kind | core/tests/test_trust_summary_render.py |
| AC-008 | integration, temp git repo with a lock commit and a later change | core/tests/test_trust_summary_lock.py |
| AC-009 | unit, render with tamper findings, with and without `[test-change]` | core/tests/test_trust_summary_render.py |
| AC-010 | unit, render with mutation evidence | core/tests/test_trust_summary_render.py |
| AC-011 | unit, render with coverage evidence above and below the minimum | core/tests/test_trust_summary_render.py |
| AC-012 | unit, render with missing, skipped, crashed and unknown-version producers | core/tests/test_trust_summary_render.py |
| AC-013 | unit, render for a chore branch | core/tests/test_trust_summary_render.py |
| AC-014 | unit, render for bugfix and hotfix branches | core/tests/test_trust_summary_render.py |
| AC-015 | unit: a PR description claiming results changes nothing in the output | core/tests/test_trust_summary_render.py |
| AC-016 | unit, fake ADO client returning 403 and 500 | core/tests/test_trust_summary_post.py |
| AC-017 | CLI test: Markdown equals the text the poster sends | core/tests/test_trust_summary_cli.py |
| AC-018 | CLI test: JSON output and its schema_version | core/tests/test_trust_summary_cli.py |
| AC-019 | unit, render: line count of the head, fold above 10 rows | core/tests/test_trust_summary_render.py |
| AC-020 | manual, pilot repo: job duration from three pipeline runs | pilot notes |

## 6. Risks, rollout, rollback
- **The summary says "clean" when it isn't.** This is the one failure that destroys trust, so the renderer is
  fail-closed: anything missing, unknown or crashed is "not measured" (AC-012), and only measured evidence counts.
- **Comment noise.** One comment per PR, updated in place (AC-002), closed so it never blocks a merge (AC-003).
- **Permission missing on the build service.** The job warns and keeps the artifact (AC-016); it never fails a PR.
- **The pipeline templates have not run in a real Azure DevOps project yet.** The first pilot PR tests this job with
  the others.
- **Rollout.** Off until a repo adds the job; on in the pilot repo first. It never blocks, so it does not need a warn
  mode. Rollback: remove the one line from `azure-pipelines-pr.yml`.

## 7. Open questions
1. Should the PR template drop its hand-filled "AC → test → result" table and point to the summary instead?
   Proposed: yes, because the pasted table is written by the agent whose work it reports on.
2. Is "no single score" right? A score is easier to quote in a management update but invites gaming the number.
3. Eval results for the ai track: in this spec (the eval gate writes an evidence file), or a follow-up spec?
4. Who reviews this spec besides the owner?
