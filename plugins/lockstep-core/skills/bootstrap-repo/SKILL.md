---
name: bootstrap-repo
description: Set up a repo for Lockstep, or upgrade it to a newer Lockstep version.
disable-model-invocation: true
---

# Set up a repo for Lockstep

Paths below are relative to this skill's folder. `scripts/bootstrap.py` needs Python 3.11+ and git, nothing else.
It never overwrites a file the repo owns: those come back as **merge** items for you to merge with the user.

## 1. Check where you are

- You must be at the root of a git repo with a clean working tree. If there are uncommitted changes, ask first; don't
  stash them yourself.
- Work on a new branch `chore/lockstep-bootstrap` (add `-YYYYMMDD` if it exists), never on main.
- Look at what exists: `pyproject.toml`, `uv.lock`, `dbt_project.yml`, `databricks.yml`, `tests/`, `evals/`, `prompts/`,
  `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `.github/copilot-instructions.md`, `.azuredevops/`,
  `azure-pipelines*.yml`, and `.lockstep/VERSION` (present means this is an upgrade).

## 2. Ask once, in one message

- **Tracks:** data, ai or both. Suggest from what you found (dbt or Databricks → data; prompts, evals or an LLM SDK → ai).
- **Jira project keys:** default `MXAAI`.
- **Lockstep version:** a tag of the Lockstep repo, or `main` if the team has no tags yet. On an upgrade, show the
  current one from `.lockstep/VERSION`.

## 3. Show the plan

```
python3 scripts/bootstrap.py --root <repo> --ref <version> --tracks <data,ai> --jira <MXAAI> --diff
```

It prints one line per file: **create**, **update** (Lockstep-owned: `.lockstep/`, `specs/_template/`), **remove**
(a Lockstep-owned file that the new version dropped) or **merge** (the repo has its own version). Summarise it for the
user: counts per action, and each merge item with what you propose. Wait for a go-ahead.

If the fetch fails (no network to GitHub), ask for a local Lockstep checkout and use `--source <path>` instead of `--ref`.

## 4. Apply, then merge by hand

Run the same command with `--apply` instead of `--diff`. Then handle each merge item. Keep everything the repo has, add
only what is missing, and show the user the diff:

| File | How to merge |
|---|---|
| `AGENTS.md` | Add the template's sections the file lacks (How work flows, Non-negotiables, Naming the criterion, Definition of done, the `lockstep:review-rules` block). Keep the repo's text; keep the whole file under 150 lines. |
| `CLAUDE.md` | Make the first line `@AGENTS.md` and add the "Claude only" notes. |
| `GLOSSARY.md` | Keep the repo's entries; add the template's entry format at the top if it has none. |
| `.claude/settings.json` | Merge the JSON: add the template's `permissions` entries and `hooks` registrations that are missing. Never remove an entry. |
| `.azuredevops/pull_request_template.md` | Add the missing sections: AC → test → result, agent used, the checklists. |
| `azure-pipelines-pr.yml` | If the repo already has a PR pipeline, add `- template: .lockstep/pipelines/lockstep-pr.yml` as its first steps instead of a second pipeline. Remove the repo's own `checkout` step there, as the template does a full checkout. |
| `lockstep.toml` | Keep the repo's values. Mention template keys the file lacks; defaults apply to them. |

## 5. Fill in the repo-specific parts

- **AGENTS.md:** replace the placeholders. "What this repo builds" comes from the README or the user. In **Commands**,
  keep only commands that exist and use the repo's real ones (`uv run` when there is a `uv.lock`, the dbt selector the
  CI uses, the bundle target names from `databricks.yml`). Delete the lines for tools the repo doesn't have.
- **pytest marker:** if the repo has pytest, register the marker in `pyproject.toml` under `[tool.pytest.ini_options]`:
  `markers = ["ac(id): acceptance criterion this test covers"]`. Merge with an existing `markers` list.
- **Copilot review rules:** run `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_review_rules --write`.
  It copies the Lockstep block from AGENTS.md into `.github/copilot-instructions.md` and keeps any rules already there.
  For repo-specific rules on top, offer the `copilot-review-instructions` skill afterwards.

- **GLOSSARY.md:** ask the user for the three to five business terms people most often mean differently (for a data
  team, usually metric definitions such as "active customer" or "net revenue") and write their entries. It grows
  with every spec after that.

## 6. Prove it works

- Run every check: `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_<name>` for `pr_size`, `test_tamper`,
  `ac_traceability` and `review_rules`. They should pass; `jira_key` fails until the branch or title has a key.
- Smoke-test a hook: `echo '{"tool_name":"Bash","tool_input":{"command":"databricks bundle deploy -t prod"}}' |
  .lockstep/hooks/run-hook.sh guard_bash` must exit 2. With `git status` as the command it must exit 0.

## 7. Commit, then hand over

Commit as `chore(lockstep): set up Lockstep <version>` (or `upgrade Lockstep to <version>`). Ask before pushing or
opening a PR; the PR title needs a Jira key. Then give the user the Azure DevOps steps that only they can do:

1. Create a pipeline from `azure-pipelines-pr.yml`, and one from `azure-pipelines-deploy.yml`. Delete the PR jobs
   for tracks the repo doesn't have. Create the variable groups and environments the two files' header comments list,
   with service principals that have no SELECT on tables holding personal data.
2. Branch policies on main, as listed in `docs/branch-policy.md`: fill in the variables at the top of
   `scripts/ado/branch-policy.sh` and run it (it uses `az repos policy`), or set them by hand. The user runs it, not you:
   it changes the repo's settings.
3. Create the prod environment's approval as `docs/branch-policy.md` describes.
4. Add GitHub Copilot as an automatic reviewer, if the project has Copilot code review.

Remind them that Copilot reads `.github/copilot-instructions.md` from the target branch, so the review rules apply to
PRs opened after this one merges.

## Upgrading later

Run the skill again with a newer version. Lockstep-owned files are updated and pruned; repo files are only ever merge
items. Read the Lockstep changelog or diff for new template sections worth merging.
