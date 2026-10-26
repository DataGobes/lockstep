# Lockstep

Skills, hooks and shared checks for spec-first, test-locked development with coding agents. Every plugin in this repo installs in both
**Claude Code** and **GitHub Copilot CLI** from the same files.

| Plugin | What it does |
|---|---|
| [`copilot-review-instructions`](plugins/copilot-review-instructions/skills/copilot-review-instructions/SKILL.md) | Generates and maintains repo-specific Copilot code review rules (`.github/copilot-instructions.md` + path-scoped `.github/instructions/*.instructions.md`) on top of the project-wide rules. Works for Azure DevOps (Azure Repos) and GitHub. |

## Install

**Claude Code**

```
/plugin marketplace add DataGobes/lockstep
/plugin install copilot-review-instructions@lockstep
```

**GitHub Copilot CLI**

```
copilot plugin marketplace add DataGobes/lockstep
copilot plugin install copilot-review-instructions@lockstep
```

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
  Unknown keys are errors, so a typo never switches a gate off. Jira project keys are set in `[jira] projects` (default `MXAAI`).
- `lockstep_checks.spec`: finds the active spec from the branch name (`feature/0042-*` -> `specs/0042-*/status.yml`).
  Try it with `PYTHONPATH=core/src python3 -m lockstep_checks.spec`.

### PR checks

Each check runs as `python -m lockstep_checks.<check>` from the repo root, locally or in Azure Pipelines, where
findings show up on the PR with file and line. Common options: `--base` (default: the PR target branch, else
`origin/main`) and `--title` (or `$LOCKSTEP_PR_TITLE`; Azure Pipelines has no built-in variable for the PR title).

| Check | Fails when |
|---|---|
| `check_test_tamper` | an existing file under `[protect] globs` is modified, renamed or deleted, or a change adds skip/xfail, `# noqa`, `type: ignore`, or disables or downgrades a dbt test. A title starting with `[test-change]` turns these into warnings. |
| `check_ac_traceability` | a tests-locked spec has a criterion without a test, a test names an unknown spec or criterion, or a spec is malformed. `--spec-only` lints specs only. |
| `check_pr_size` | more than 800 changed lines (unless `[large-approved]` is in the title) or more than 100 files. Warns above 400. Generated files don't count. |
| `check_jira_key` | the title and branch have no issue key of a `[jira] projects` project, have several keys, or the key differs from the spec's. |

Tests name criteria with the spec id, because every spec numbers from AC-001: `@pytest.mark.ac("0042/AC-001")`,
dbt unit test `ac_0042_001_<what>`, `meta: {ac: 0042/AC-001}`, or an `ac` field `0042/AC-001` in an eval row. Register the
marker in the product repo's `pyproject.toml`: `markers = ["ac(id): acceptance criterion this test covers"]`.

### Agent hooks

`core/hooks/run-hook.sh <hook>` runs a hook from `lockstep_checks.hooks` with the agent's event JSON on stdin. Exit 0
allows and exit 2 blocks. Hooks fail closed: a crash, bad input or a missing Python 3.11+ blocks. Claude Code and Copilot
(CLI and VS Code) both read the registration in a product repo's `.claude/settings.json`; see
[`templates/claude-settings.json`](templates/claude-settings.json), which expects `core/` copied to `.lockstep/`.

| Hook | Event | Blocks when |
|---|---|---|
| `protect_tests` | PreToolUse on Edit, Write, MultiEdit, NotebookEdit | the active spec is tests-locked and the file matches `[protect] globs` and exists on origin/main. New files are allowed. Copilot's `apply_patch` payloads are parsed too. |
| `guard_bash` | PreToolUse on Bash, PowerShell | the command targets prod, force-pushes, deletes main, skips tests with `-k`/`--deselect`/`--ignore`, or rewrites history while on main. |
| `screen_pii` | UserPromptSubmit | the prompt has an email, phone number, valid IBAN or a `[pii] columns` name, or the active spec has `pii: yes`. Claude only: Copilot ignores this hook's result, which is intended. |

Run the tests with `cd core && uv run --with pytest python -m pytest`.

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
