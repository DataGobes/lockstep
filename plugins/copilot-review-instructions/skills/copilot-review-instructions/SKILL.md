---
name: copilot-review-instructions
description: Create or update repository-specific GitHub Copilot code review instructions (.github/copilot-instructions.md plus path-scoped .github/instructions/*.instructions.md with applyTo) that sit on top of project- or org-wide review rules, for repos on Azure DevOps (Azure Repos) or GitHub. Scans the repo's real conventions, asks about review pain points, proposes 10-20 checkable rules for approval, then writes or merges the files without losing manual edits. Use this whenever someone wants Copilot PR reviews to reflect a repo's own architecture, conventions or gotchas, mentions copilot-instructions.md, *.instructions.md or applyTo, says Copilot review comments are too generic or noisy, or wants to refresh existing Copilot review rules, even if they don't name the files.
---

# Copilot review instructions for this repo

Produce a small set of repo-specific, diff-checkable review rules that **add to** the project-wide rules, never repeat them,
and put them where Copilot code review picks them up. The user's knowledge of review pain outranks anything inferred from code.

Paths below are relative to this skill's folder. Use `python3` (or `python` on Windows) for the scripts. They need only the standard library.

## Workflow

### 1. Orient

- Make sure you are at a git repo root with a clean working tree. If there are uncommitted changes, ask before going on;
  don't stash them yourself.
- Run `python3 scripts/scan_repo.py --root <repo>` and keep the JSON. It gives you the host (`azure-devops` / `github`),
  default branch, stacks with evidence, layout, naming-prefix stats, existing instruction files and files to sample.
- Read `references/platform-facts.md`. On **Azure DevOps**, instructions are read from the PR's *target* branch, and
  repo rules override project rules. Both facts shape steps 5 and 7.

### 2. Load the project-wide (upstream) instructions

These live outside the repo (Azure DevOps project/org settings, or GitHub org settings). Get them in this order:
1. If `COPILOT_REVIEW_UPSTREAM_CMD` is set, run it; its stdout is the text.
2. Else if `COPILOT_REVIEW_UPSTREAM_FILE` is set, read that file.
3. Else ask the user to paste them or give a file path. Mention that setting one of the env vars skips this question next time.

Save the text to a temp file outside the repo (for the linter) and **never commit it**. If the user has none or can't
get them, continue, but say that duplicate-checking against project rules was skipped.
Also read any repo files Copilot may already use: existing `copilot-instructions.md` / `*.instructions.md`, and
`AGENTS.md` / `CLAUDE.md` on GitHub.

### 3. Learn the repo's real conventions

Read the sampled files from the scan (2–3 per major area, plus the hot spots), the CI pipeline, and lint/format configs
(`pyproject.toml`, `.sqlfluff`, `.pre-commit-config.yaml`). Look for:
- **Boundaries:** which layer or package may depend on which (dbt staging/intermediate/marts, `src/` vs notebooks, shared libs).
- **Mandatory wrappers:** config loaders, HTTP clients, logging setup, macros, base classes everything goes through.
- **Error-handling contracts:** custom exception types, retry policy, what must never be swallowed.
- **Naming and placement:** prefixes, file-per-entity rules, where tests and YAML properties live.
- **Domain rules:** units, currencies, time zones, soft deletes, PII columns.
- **Visible friction:** TODO/FIXME notes about reviews, one file breaking a pattern all its siblings follow.

Record each finding with `path:line` evidence. A convention needs at least two occurrences. Note what linters and
CI already enforce; those are not rules.

### 4. Ask 2–3 targeted questions

Ask about review pain, with concrete options grounded in what you found, e.g.
"In dbt PRs, what do reviewers correct most: models reading `source()` outside staging (seen in
`int_shipments_joined.sql:12`), missing PK tests, or naming?" Good topics: what reviewers keep correcting, which boundary
keeps getting crossed, and what Copilot currently flags that is noise or misses that matters. Ask all of them in one go.
If the user already gave pain points in the request, don't ask again; at most confirm a gap.
**Their answers outrank your inferences.** If code contradicts an answer, mention it once, then follow the user.

### 5. Draft the rules and get approval

Read `references/rule-quality.md` and apply its checklist to every rule. Then:
- 10–20 rules in total (on re-runs: existing plus new, preferring replacement over growth).
- Cross-cutting rules go in `copilot-instructions.md`; language- or folder-specific rules go in path-scoped files with narrow
  `applyTo` globs (`references/file-format.md`).
- Drop anything already in the upstream text (even reworded), already in existing files, or enforced by tooling.
- Flag any rule that **conflicts** with a project rule. On Azure DevOps the repo rule would silently win, so the user must
  choose: drop it, or keep it as a deliberate override that the PR description will state.

Show the proposal **before writing anything**, in this shape:

```
Target: <host> · <org/project/repo> · files go in .github/ (Copilot reads them from <target|head> branch)

copilot-instructions.md (all files) – N rules
  1. <rule>                                   [source: user answer | path:line, path:line]
dbt.instructions.md (applyTo: "dbt/models/**/*.sql,…" → 14 files) – N rules
  …
Existing rules: K kept unchanged · proposed changes: <change/remove/move items with reason>
Skipped as duplicates of project rules: <short list> · skipped as tool-enforced: <short list>
Conflicts with project rules: <none | item + your recommendation>
Snippets: rules #3, #7 get bad/good examples from <file>
```

Apply what the user changes, and wait for an explicit go-ahead.

### 6. Write the files

- Create the branch first (`references/file-format.md` › Branch).
- New files: use the templates in `references/file-format.md`.
- Existing files: follow the **update protocol** in that file. Keep every manual edit, make targeted inserts only, and apply
  only the approved change/remove/move items.
- Run `python3 scripts/lint_instructions.py --root <repo> --project-instructions <upstream temp file>`.
  Fix every ERROR. Fix each WARN, or tell the user why it stays (e.g. a glob for files that don't exist yet).
- Check `git diff`: every removed line must trace back to an approved item.

### 7. Commit, then ask about the PR

Commit using the message format in `references/file-format.md`. Then ask whether to push and open a PR. Only on yes:
push, and create the PR with `az repos pr create` (Azure DevOps) or `gh pr create` (GitHub), or give the PR-creation URL
if the CLI isn't available. Use the PR description template, including any deliberate override of a project rule, so
the owner of the project-level instructions isn't surprised.

Finish with:
- what was written (files, rule counts);
- **when it takes effect:** on Azure DevOps only after merge into the target branch, so this PR's own review won't use the
  new rules. On GitHub this PR's review already uses them;
- how to test them: offer the A/B procedure in `references/ab-testing.md` (same diff, with vs without the rules) and the
  scorecard for refining rules that were ignored, misread or noisy.

## Re-running later

The skill is meant to be re-run after reviews show gaps, or when the repo changes shape. The same workflow applies.
In step 4, ask what Copilot missed or over-flagged since the last run. In step 5, list the proposed edits to existing rules
explicitly. Never regenerate a file from scratch.
