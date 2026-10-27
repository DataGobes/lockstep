---
id: 0003
title: Bootstrap trims PR pipeline jobs to the chosen tracks
owner: <engineer>
reviewer: <engineer>
---

# Bootstrap trims PR pipeline jobs to the chosen tracks

## 1. Problem and outcome
`bootstrap.py --tracks` writes the chosen tracks into `lockstep.toml`, but copies `azure-pipelines-pr.yml` with the
jobs of every track. The template's header says "the bootstrap-repo skill does this", yet nothing does: a repo on one
track gets jobs it cannot run (dbt Slim CI and the Databricks bundle without a dbt project, or an eval gate without
evals), and someone deletes them by hand. That happened when Lockstep bootstrapped itself.

Outcome: a repo bootstrapped for the first time with one track gets a PR pipeline that has only that track's jobs,
with no hand edits. A repo that already has the file gets a merge item whose diff proposes the trimmed file.

## 2. Scope / non-goals
- In scope: `plugins/lockstep-core/skills/bootstrap-repo/scripts/bootstrap.py` (the content it plans for
  `azure-pipelines-pr.yml`), and removing the sentence "Delete the PR jobs for tracks the repo doesn't have." from
  step 7 of the bootstrap-repo `SKILL.md`.
- Track jobs: data is `dbt` and `bundle`; ai is `evals`. Every other job and stage (`lockstep`, `quality`,
  `mutation`, `summary`) belongs to every repo.
- A **job block** is the line `      - job: <name>` through the blank line that ends it; in the template every job
  ends with exactly one blank line before the next `- job:` or `- stage:` line. Removing a block that way leaves no
  doubled blank line.
- The tracks are a set: `--tracks data,ai`, `--tracks ai,data` and no `--tracks` (the default) all mean both.
- Out of scope: `azure-pipelines-deploy.yml` (it has no per-track jobs); `templates/azure-pipelines-pr.yml` itself,
  which keeps every job; the vendored `.lockstep/pipelines/*.yml` files, which are copied whole.
- Not a goal: editing a repo's own pipeline file. A repo file is never overwritten.
- Not a goal: rewording the template's header comment; a trimmed file keeps it as it is.

## 3. Acceptance criteria (each testable)

- AC-001 WHEN bootstrap plans a repo with `--tracks ai` THE SYSTEM SHALL plan `azure-pipelines-pr.yml` as the
  template with the `dbt` and `bundle` job blocks removed and every other line unchanged.
- AC-002 WHEN bootstrap plans a repo with `--tracks data` THE SYSTEM SHALL plan `azure-pipelines-pr.yml` as the
  template with the `evals` job block removed and every other line unchanged.
- AC-003 WHEN bootstrap plans a repo with both tracks (`--tracks data,ai`, `--tracks ai,data`, or no `--tracks`)
  THE SYSTEM SHALL plan `azure-pipelines-pr.yml` byte-identical to the template.
- AC-004 IF the repo already has an `azure-pipelines-pr.yml` that differs from the trimmed template THEN THE SYSTEM
  SHALL plan it as a merge item and leave the file unchanged after `--apply`.
- AC-005 WHEN bootstrap runs again with the same tracks on a repo whose `azure-pipelines-pr.yml` is still the file the
  earlier run created THE SYSTEM SHALL plan it as already up to date.
- AC-006 WHEN bootstrap runs with `--tracks ai --diff` on a repo whose own `azure-pipelines-pr.yml` differs THE
  SYSTEM SHALL show a diff with no added line `      - job: dbt` or `      - job: bundle`.

Never delete or renumber a criterion. When a later spec replaces one, strike it and point to its replacement, e.g.
`- ~~AC-002~~ superseded by 0057/AC-001`.

## 4. Interfaces and data contract
- Input: `--tracks` (unchanged: a non-empty subset of `data`, `ai`), and `templates/azure-pipelines-pr.yml` from the
  Lockstep source.
- Output: the `Action` for `azure-pipelines-pr.yml` in `plan()`; its `content` is what `--apply` writes and what
  `--diff` compares against.
- No contract change: the command-line flags, the action kinds and the JSON plan output stay the same.
- Consumers: the bootstrap-repo skill, and product repos on their first bootstrap or an upgrade.

## 5. Test and eval plan

| AC | Test | Location |
|----|------|----------|
| AC-001 | pytest: plan with `ai`, compare to the template minus the `dbt` and `bundle` job blocks | `plugins/lockstep-core/skills/bootstrap-repo/tests/test_pipeline_tracks.py` |
| AC-002 | pytest: plan with `data`, compare to the template minus the evals block | same file |
| AC-003 | pytest: plan with `data,ai`, `ai,data` and the default, compare bytes with the template | same file |
| AC-004 | pytest: repo with its own pipeline file, plan says merge, apply leaves it | same file |
| AC-005 | pytest: apply with `ai`, plan again with `ai`, action is same | same file |
| AC-006 | pytest: repo with its own pipeline file, `--diff` output has no line `+      - job: dbt` or `+      - job: bundle` | same file |

The expected file is built in the test from the template's lines: drop the lines from the literal `      - job: dbt`
line up to the literal `      - job: evals` line (AC-001), or from the literal `      - job: evals` line up to the
literal `  - stage: summary` line (AC-002). The tests never call the trimming code to build what they expect.

## 6. Risks, rollout, rollback
- Risk: a later template edit (a new job, a renamed job) silently breaks the trimming. AC-001 and AC-002 compare the
  whole file, so such an edit fails the tests.
- Rollout: ships in the next Lockstep release. New repos get the trimmed file. Repos bootstrapped earlier keep their
  own file, which is a merge item on their next `/bootstrap-repo` run (AC-004); its diff proposes the trimmed file
  (AC-006).
- Rollback: revert the commit; repos keep the files they already have.

## 7. Open questions
None. Settled with the author on 2026-10-27: the header comment stays as it is, a merge diff proposes the trimmed
template (AC-006), and the hand-delete sentence leaves `SKILL.md` in this PR.
