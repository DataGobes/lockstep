# Lockstep

Skills, hooks and shared checks for spec-first, test-locked development with coding agents. Every plugin in this repo installs in both
**Claude Code** and **GitHub Copilot CLI** from the same files.

| Plugin | What it does |
|---|---|
| `lockstep-core` | [`lockstep`](plugins/lockstep-core/skills/lockstep/SKILL.md): run `/lockstep` any time; it reads each spec's status and branches and names the next step and skill. [`bootstrap-repo`](plugins/lockstep-core/skills/bootstrap-repo/SKILL.md): sets up a product repo for Lockstep, or upgrades it. Copies the checks and hooks into `.lockstep/`, writes the config and templates, merges with what the repo already has, and lists the Azure DevOps settings to make by hand. [`spec`](plugins/lockstep-core/skills/spec/SKILL.md): drafts a spec from a Jira issue with numbered EARS acceptance criteria, non-goals, a test plan and open questions, and stops for PII work in Claude. [`tests-first`](plugins/lockstep-core/skills/tests-first/SKILL.md): writes failing tests for an approved spec, proves each is red for the right reason (an assertion, not an import error), and opens the test PR that locks them. [`implement`](plugins/lockstep-core/skills/implement/SKILL.md): builds a tests-locked spec in its own worktree and stops instead of bending a test. [`self-review`](plugins/lockstep-core/skills/self-review/SKILL.md): reviews the diff in two separate passes, standards (rules, changed tests, invented APIs, error masking) and spec (each criterion met, missing or wrong, plus scope creep), and fills in the PR description. [`bugfix`](plugins/lockstep-core/skills/bugfix/SKILL.md): the light lane for bugs, a bug report, a new regression test shown red, then the smallest fix, in one `bugfix/` PR (after SDTRD's Fast-Track Protocol). [`baseline`](plugins/lockstep-core/skills/baseline/SKILL.md): brings existing code into Lockstep; ranks areas by how often they change, describes what one does today in a baseline spec, and pins it with tests that pass now, adopting existing tests where they fit. [`retro-capture`](plugins/lockstep-core/skills/retro-capture/SKILL.md): gathers reverts, `[test-change]` PRs and fixes from git history, and turns a retro into one change to the repo's rules, as a PR. |
| `lockstep-ai` | [`eval-case`](plugins/lockstep-ai/skills/eval-case/SKILL.md): writes golden eval cases for a spec's criteria and checks each file for a unique id, a known `ac` reference, inputs, expectations and personal data. |
| `lockstep-data` | [`dbt-impact`](plugins/lockstep-data/skills/dbt-impact/SKILL.md): from the branch and prod manifests, lists changed and downstream models, enforced contracts that need a new version, the Unity Catalog lineage query for consumers outside dbt, and a dbt-audit-helper data diff per model. |
| [`copilot-review-instructions`](plugins/copilot-review-instructions/skills/copilot-review-instructions/SKILL.md) | Generates and maintains repo-specific Copilot code review rules (`.github/copilot-instructions.md` + path-scoped `.github/instructions/*.instructions.md`) on top of the project-wide rules. Works for Azure DevOps (Azure Repos) and GitHub. |

Each skill has a page for people in [docs/skills/](docs/skills/README.md). [Why Lockstep writes the tests
first](docs/why-tests-first.md) answers the usual critique of test-first agent workflows.

## Install

**Claude Code**

```
/plugin marketplace add DataGobes/lockstep
/plugin install lockstep-core@lockstep
/plugin install lockstep-data@lockstep   # data track
/plugin install lockstep-ai@lockstep     # ai track
/plugin install copilot-review-instructions@lockstep
```

**GitHub Copilot CLI**

```
copilot plugin marketplace add DataGobes/lockstep
copilot plugin install lockstep-core@lockstep
copilot plugin install lockstep-data@lockstep   # data track
copilot plugin install lockstep-ai@lockstep     # ai track
copilot plugin install copilot-review-instructions@lockstep
```

Then, in a product repo, run `/bootstrap-repo` once and `/lockstep` whenever you're unsure what comes next.
`lockstep`, `bootstrap-repo` and `retro-capture` run only when you type them; the other skills also start on their own
when the conversation calls for them.

Update later with `/plugin update` (Claude Code) or `copilot plugin update copilot-review-instructions`.

## Use `copilot-review-instructions`

Open Claude Code or Copilot CLI in the repo you want rules for and ask, for example:

> Set up Copilot review instructions for this repo.

The skill:
1. reads the project-wide instructions (see below) so it never duplicates them;
2. scans the repo (stacks, layout, naming, CI, linters) and samples real code;
3. asks you 2–3 questions about what reviewers keep correcting;
4. proposes 10–20 rules that can be checked in a diff, with their sources, and waits for your approval;
5. writes or **merges** the files on a branch, keeping manual edits, and lints them;
6. commits, then asks before pushing or opening a PR.

Run it again whenever Copilot misses something or over-flags. It updates the files in place.

### Project-wide instructions

On Azure DevOps these live in *Project settings → Copilot code review* (and optionally at organization level). There is
no documented API, so the skill gets them, in this order, from:

| Source | Set up |
|---|---|
| `COPILOT_REVIEW_UPSTREAM_CMD` | A command that prints the project/org instructions to stdout (e.g. your own API/CLI script). |
| `COPILOT_REVIEW_UPSTREAM_FILE` | Path to an exported copy. |
| Neither | The skill asks you to paste them. |

### Azure DevOps: when the rules take effect

Copilot on Azure Repos reads instruction files from the PR's **target branch**. The PR that adds the rules is reviewed
with the old ones, and the new rules apply to PRs opened after the merge. To measure their effect before or after merging, use
the A/B procedure in
[`references/ab-testing.md`](plugins/copilot-review-instructions/skills/copilot-review-instructions/references/ab-testing.md).

On Azure DevOps, repo rules also **override** project rules when they conflict, so the skill flags every conflict and
lists deliberate overrides in the PR description.

## Shared core (`core/`)

The `lockstep-checks` Python package (import name `lockstep_checks`; stdlib only, Python 3.11+) holds the logic that hooks and Azure Pipelines both run, so
the two can never disagree. It starts with:

- `lockstep_checks.config`: loads a repo's `lockstep.toml` (template in [`templates/lockstep.toml`](templates/lockstep.toml)).
  Unknown keys are errors, so a typo never switches a gate off. Jira project keys are set in `[jira] projects` (default `MXAAI`); a team without Jira sets `[jira] required = false`, so specs, branches and PRs need no key.
  `[enforcement]` puts each gate in `warn` or `enforce` mode: new repos start in warn and switch on the evidence, see
  [Warn first, then enforce](docs/enforcement-modes.md).
- `lockstep_checks.spec`: finds the active spec from the branch name (`feature/0042-*` -> `specs/0042-*/status.yml`).
  Try it with `PYTHONPATH=core/src python3 -m lockstep_checks.spec`.

### PR checks

Each check runs as `python -m lockstep_checks.<check>` from the repo root, locally or in Azure Pipelines, where
findings show up on the PR with file and line. Common options: `--base` (default: the PR target branch, else
`origin/main`) and `--title` (or `$LOCKSTEP_PR_TITLE`; Azure Pipelines has no built-in variable for the PR title).

| Check | Fails when |
|---|---|
| `check_test_tamper` | an existing file under `[protect] globs` is modified, renamed or deleted, or a change adds skip/xfail, `# noqa`, `type: ignore`, or disables or downgrades a dbt test. On a feature branch, the spec's own tests are protected from the commit where the test PR merged into it. A title starting with `[test-change]` turns these into warnings. |
| `check_ac_traceability` | a tests-locked spec has a criterion without a test, a test names an unknown spec or criterion, or a spec is malformed (including criteria not in the `[specs] ac_format`: EARS, Given/When/Then or either). From `approved` on, a spec that takes the research and design step also needs `research.md` with a decision and `design.md` without open questions. `--spec-only` lints specs only. |
| `check_pr_size` | more than 800 changed lines (unless `[large-approved]` is in the title) or more than 100 files. Warns above 400. Generated files don't count. |
| `check_jira_key` | the title and branch have no issue key of a `[jira] projects` project, have several keys, or the key differs from the spec's. With `required = false`, a missing key passes. |
| `check_spec_required` | code changes on a branch without a spec at the right status: `feature/<id>-` needs it tests-locked, `test/<id>-` approved, `spec/<id>-` may change only specs and docs. `chore/` needs no spec; `bugfix/` and `hotfix/` need a bug report and a new regression test; `baseline/<id>-` changes only tests, specs and docs, for a baseline spec that is implemented by the end of the PR ([baseline specs](docs/baseline-specs.md)). Specs, docs and Markdown never need one. Follows SDTRD's chore exemption and Fast-Track bug lane. |
| `check_living_specs` | with `[specs] living = true`: `specs/living/<capability>.md` is missing or stale, or a spec past draft names no capability. `--write` regenerates them ([living specs](docs/living-specs.md)). Off by default. |
| `check_review_rules` | the Lockstep review rules in `.github/copilot-instructions.md` are missing or differ from the block in `AGENTS.md`. `--write` updates the copy and keeps the repo's own rules. |

Tests name criteria with the spec id, because every spec numbers from AC-001: `@pytest.mark.ac("0042/AC-001")`,
dbt unit test `ac_0042_001_<what>`, `meta: {ac: 0042/AC-001}`, or an `ac` field `0042/AC-001` in an eval row. Register the
marker in the product repo's `pyproject.toml`: `markers = ["ac(id): acceptance criterion this test covers"]`.

### Azure Pipelines

[`core/pipelines/lockstep-pr.yml`](core/pipelines/lockstep-pr.yml) is a steps template that runs all the checks on a PR.
A product repo includes it from its PR pipeline, as in [`templates/azure-pipelines-pr.yml`](templates/azure-pipelines-pr.yml):

```yaml
steps:
  - template: .lockstep/pipelines/lockstep-pr.yml
```

- **Branch policy, not a trigger.** Azure Repos ignores `pr:` in YAML. Add the pipeline to main's branch policy as a
  required *Build validation*, so a red check blocks the merge.
- **Full clone.** The template checks out with `fetchDepth: 0`, because the checks diff against the target branch.
- **PR title.** `lockstep_checks.ado_pr_title` reads the title from the REST API with `System.AccessToken` and sets
  `LOCKSTEP_PR_TITLE`. The project's build service needs Read on the repository, which it has by default.
- Every check runs even when an earlier one fails, and findings appear on the PR with file and line.
- **Warn mode.** A check in `warn` mode passes and reports what it would have blocked, and tags the run
  `lockstep-would-block-<check>` so the team can count it ([how](docs/enforcement-modes.md)).

The other PR gates are steps templates in `core/pipelines/` too, one job each in the root pipeline. Keep the ones for
the repo's tracks; each gate can be switched off by a parameter until the repo is ready for it.

| Template | Gate | Track |
|---|---|---|
| `python-quality.yml` | pre-commit on changed files, pyright, pytest with diff-cover (80% of changed lines), pip-audit, Bandit (high) | all |
| `dbt-slim-ci.yml` | `dbt build --select state:modified+ --defer` against the prod manifest from the deploy pipeline | data |
| `bundle-validate.yml` | `databricks bundle validate` for the dev target | data |
| `eval-gate.yml` | the repo's eval command, only when the PR touches prompts, evals or LLM code | ai |
| `mutation-report.yml` | report only: mutmut on the PR's changed modules, score and missed mutants as warnings ([why](docs/mutation-testing.md)) | all |

The Databricks gates read their credentials from a variable group (`lockstep-ci` in the root pipeline); use a CI
service principal without SELECT on tables that hold personal data. None of these templates has run in a real
Azure DevOps project yet, so the first pilot PR is their test.

**Deploy.** [`templates/azure-pipelines-deploy.yml`](templates/azure-pipelines-deploy.yml) runs on every merge to main:
staging, then prod, each a deployment job from `core/pipelines/lockstep-deploy.yml` (bundle deploy, dbt build of what
changed since the last prod deploy, smoke tests, evals). Prod waits for the approval on its Azure DevOps environment,
which must not let the person who merged approve their own run, and publishes the dbt manifest that Slim CI defers to.

### Templates for a product repo

The `bootstrap-repo` skill copies these and merges them with files the repo already has.

| Template | Goes to | What it is |
|---|---|---|
| [`AGENTS.md`](templates/AGENTS.md) | `AGENTS.md` | Workflow, non-negotiables, commands and definition of done for every agent, plus the Lockstep review rules block that `check_review_rules` copies for Copilot code review, which doesn't read AGENTS.md. |
| [`CLAUDE.md`](templates/CLAUDE.md) | `CLAUDE.md` | Imports AGENTS.md and adds Claude-only notes. |
| [`docs/branch-policy.md`](templates/docs/branch-policy.md), [`ado/branch-policy.sh`](templates/ado/branch-policy.sh) | `docs/`, `scripts/ado/` | The branch policies main needs (reviewers, squash, build validation, path-based reviewers) and an `az repos policy` script that sets them, for a person to run. |
| [`azuredevops/pull_request_template.md`](templates/azuredevops/pull_request_template.md) | `.azuredevops/pull_request_template.md` | Spec link, AC → test → result table, agent used, PII routing and the reviewer checklist. |
| [`lockstep.toml`](templates/lockstep.toml), [`claude-settings.json`](templates/claude-settings.json), [`specs/_template/`](templates/specs/_template), [`azure-pipelines-pr.yml`](templates/azure-pipelines-pr.yml), [`azure-pipelines-deploy.yml`](templates/azure-pipelines-deploy.yml) | repo root, `.claude/settings.json`, `specs/_template/`, repo root | Config, agent permissions and hooks, the spec template (with `design/research.md` and `design/design.md` for large specs), and the PR and deploy pipelines. |

### Agent hooks

`core/hooks/run-hook.sh <hook>` runs a hook from `lockstep_checks.hooks` with the agent's event JSON on stdin. Exit 0
allows and exit 2 blocks. Hooks fail closed: a crash, bad input or a missing Python 3.11+ blocks. Claude Code and Copilot
(CLI and VS Code) both read the registration in a product repo's `.claude/settings.json`; see
[`templates/claude-settings.json`](templates/claude-settings.json), which expects `core/` copied to `.lockstep/`.

| Hook | Event | Blocks when |
|---|---|---|
| `protect_tests` | PreToolUse on Edit, Write, MultiEdit, NotebookEdit | the active spec is tests-locked and the file matches `[protect] globs` and exists on origin/main, or on a feature branch at the commit where the test PR merged. New files are allowed. Copilot's `apply_patch` payloads are parsed too. |
| `guard_bash` | PreToolUse on Bash, PowerShell | the command targets prod, force-pushes, deletes main, skips tests with `-k`/`--deselect`/`--ignore`, or rewrites history while on main. |

A prompt-screening PII hook is parked: naming a column such as `email` in a prompt is not sending its data, so a
word-based screen blocks too much. Until it returns, `pii: yes` in a spec's status.yml is the signal to work in Copilot.

Run the tests with `cd core && uv run --with pytest python -m pytest`, and the skill scripts' with
`uv run --with pytest python -m pytest plugins/lockstep-core plugins/lockstep-data plugins/lockstep-ai tools/tests`.
`python3 tools/check_release.py` checks that the marketplace, plugin versions, README and docs agree; CI runs all of
these and `plugin validate --strict` on every pull request. Releases are described in [CHANGELOG.md](CHANGELOG.md).

## Repo layout

```
.claude-plugin/marketplace.json          # one marketplace, read by Claude Code and Copilot CLI
plugins/<plugin>/
  .claude-plugin/plugin.json             # one manifest, read by both tools
  skills/<skill>/
    SKILL.md                             # workflow (keep it short)
    references/                          # loaded only when needed
    scripts/                             # deterministic helpers, stdlib-only Python
    evals/                               # test cases (claude plugin eval format)
```

To add a skill: create `plugins/<name>/` the same way, add an entry to `.claude-plugin/marketplace.json`, and run
`claude plugin validate .` before you push. Write SKILL.md in tool-neutral language ("ask the user", not tool names)
so it behaves the same in both tools.
