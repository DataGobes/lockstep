# Warn first, then enforce

Every Lockstep gate that can stop work runs in one of two modes, set per check in `lockstep.toml`:

- **`enforce`** blocks: the hook stops the agent's edit, the CI check fails the PR.
- **`warn`** lets the change through, says it *would have been blocked* and why, and counts it.

A new repo starts in `warn`, so nobody is stuck on day one. After a few weeks the team has real numbers on how often
each gate fired, and switches gates to `enforce` one by one, on that evidence rather than on opinion.

Warn mode came from Mohammed's point that Lockstep should encourage people to use it, not only block them. A gate
that blocks before the team trusts it gets worked around; a gate that has shown its value gets kept.

## Configure

```toml
[enforcement]
default = "warn"               # the mode for every check not listed below
test_tamper = "enforce"        # one line per check overrides the default
```

Checks: `protect_tests` (the hook on edits to locked tests), `test_tamper`, `spec_required`, `ac_traceability`,
`jira_key`, `pr_size`, `review_rules`, `living_specs`. A repo without an `[enforcement]` table enforces everything, as
in 0.1.0, so upgrading never weakens a gate silently.

Three things block in either mode:

- The **`guard_bash`** hook (prod deploys, force-pushes, history rewrites on main). A warning after a prod deploy is
  too late, so it is not configurable.
- A **broken `lockstep.toml` or `status.yml`**: the gate cannot tell what it would have decided.
- A **hook that crashes**: hooks fail closed.

## Count what would have been blocked

**In CI (team-wide).** Each check that fires tags the pipeline run: `lockstep-would-block-<check>` in warn mode,
`lockstep-blocked-<check>` in enforce mode. Filter the PR pipeline's runs by tag in Azure DevOps, or count them with
the REST API:

```text
GET https://dev.azure.com/{org}/{project}/_apis/build/builds?definitions={pipelineId}&tagFilters=lockstep-would-block-test_tamper&minTime=2026-11-01&api-version=7.1
```

A PR runs the pipeline on every push, so count distinct PRs (the run's `sourceBranch`, `refs/pull/<id>/merge`), not
runs. The warnings also show on the PR itself, so the author and reviewer see them.

**On a laptop (hooks).** Each block and each warn-mode pass is appended to `.git/lockstep/hook-events.jsonl`, inside
`.git` so it is never committed. It records what only the agent's hooks see: an agent that touched a locked test and
then undid it never reaches CI. Print the counts with:

```bash
PYTHONPATH=.lockstep/src python3 -m lockstep_checks.hooks.events
```

Agents are told (AGENTS.md) to treat a warn-mode message like a block. Not every agent shows a hook's message when the
hook allows the call, so the CI warning on the PR is the one everyone sees.

## When to switch a gate to enforce

Review the would-block list per gate, for example at the pilot retro (`/retro-capture`). For each warning, ask: would
blocking have been right?

| What the warnings show | Do |
|---|---|
| Mostly real problems (a weakened test, code without a spec) | Switch the gate to `enforce`. |
| Mostly false alarms | Fix the cause first (`[protect] globs`, `[lanes]`, a lane the team needs), keep `warn`. |
| Hardly any warnings | Switch to `enforce`; it costs nothing. |
| Many, and people work around them | Talk to the team before enforcing; the workflow may need to change. |

Switch one gate at a time, so a jump in blocks points at one cause. A good order: `test_tamper` and `protect_tests`
first (they protect the core promise, that agents can't change the tests they are judged by), then `spec_required`
and `ac_traceability`, then `jira_key`, `pr_size` and `review_rules`. Once every gate enforces, delete the overrides
and set `default = "enforce"`.

When `test_tamper` enforces, a deliberate test change still has its way through: a separate PR titled
`[test-change] ...`, which the required reviewer approves.
