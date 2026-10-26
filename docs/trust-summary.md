# The Lockstep summary on every PR

A reviewer of an agent-written PR wants to know one thing first: can I trust this change? Lockstep already has the
evidence: every criterion has a test, the tests were locked before the code, nobody weakened them, and the mutation
report says how strong they are. The summary puts that evidence in one comment on the PR, computed by the pipeline,
so nobody has to dig through logs and nobody has to take the author's or the agent's word for it.

```
- ❌ Tests: 1 of 3 criteria have a passing test; 1 test not as expected. Next: Fix the code until every test passes…
- ✅ Coverage: 86% of changed lines covered (minimum 80%).
- ✅ Lock: tests locked at 3f2a9c1 on 2026-10-20; no protected file changed since.
- ✅ Test tamper: no locked test weakened.
- ℹ️ Mutation: mutation score 82%: 41 of 50 mutants caught, 9 missed (report only).

| Criterion   | Test                            | Result |
| 0042/AC-001 | tests/test_churn.py::test_rate  | failed |
```

When everything is clean the comment starts with one line that says so. When something isn't, it starts with each
line that isn't, and the next step that fixes it. It is spec [0001](../specs/0001-pr-trust-summary/spec.md).

## What it trusts

- **Only this pipeline run.** Each job writes what it measured to `lockstep-evidence/<producer>.json` and publishes
  it as an artifact. The summary reads those files, git history and the target branch's `lockstep.toml`. It never
  reads the PR description, so a pasted table can't make a PR look better than its run.
- **Nothing it didn't see.** A job that was skipped, crashed or left no file shows as **not measured**, with the
  reason, and the summary is then not clean. An evidence file in a format it doesn't know is not measured too.
- **No single score.** Each signal stands on its own, so there is no number to optimise.

| Signal | From | Clean when |
|---|---|---|
| Tests | the quality job's pytest run (`-p lockstep_checks.pytest_evidence`) | every criterion has a passing test and no other test fails. In a PR into a feature branch, the spec's new tests must fail on an assertion or `NotImplementedError` instead |
| Coverage | diff-cover in the quality job (`lockstep_checks.evidence coverage`) | changed-line coverage is at least the job's minimum |
| Lock | git, in the summary job (feature branches) | no protected file that existed at the lock commit has changed since |
| Test tamper | `check_test_tamper` in the checks job | no blocking finding. A `[test-change]` PR lists each file as an approved change instead: not clean, but expected |
| Mutation | the mutation job | report only: the score never makes the summary unclean |

The PR template no longer asks for a hand-filled AC → test → result table; it points to the comment.

## Set it up

`templates/azure-pipelines-pr.yml` has two stages: the checks, then a summary stage that runs whether they passed or
failed:

```yaml
  - stage: summary
    dependsOn: checks
    condition: always()
    jobs:
      - job: summary
        steps:
          - template: .lockstep/pipelines/trust-summary.yml
```

Give the project's build service **Contribute to pull requests** on the repository. The comment's thread is created
closed, so a "resolve all comments" policy never waits on it. If posting fails, the step warns with the cause and
keeps the summary as the `lockstep-summary` artifact; it never fails the PR.

## Run it locally

```bash
PYTHONPATH=.lockstep/src python3 -m lockstep_checks.trust_summary --evidence lockstep-evidence
PYTHONPATH=.lockstep/src python3 -m lockstep_checks.trust_summary --json   # for tools and dashboards
```

The JSON carries `schema_version` (1 today). A dashboard across PRs or an Azure DevOps status badge can read it
without any change to the jobs that produce the evidence.

## Not yet

- dbt unit test results and eval results are not evidence yet, so a criterion tested only by a dbt unit test or an
  eval case shows "no test" and the Tests line is not clean. Each is a new producer, with no change to the summary.
- The summary job's run time (AC-020 asks at most 60 seconds) is measured on the pilot repo.
