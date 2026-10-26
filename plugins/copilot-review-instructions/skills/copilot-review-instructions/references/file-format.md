# File layout, templates and the update protocol

## Which files to write

```
.github/                                  # or .azuredevops/ if the repo already uses it (platform-facts.md)
  copilot-instructions.md                 # cross-cutting rules only
  instructions/
    dbt.instructions.md                   # applyTo: "dbt/models/**/*.sql,dbt/models/**/*.yml,..."
    python.instructions.md                # applyTo: "src/**/*.py,tests/**/*.py"
    pipelines.instructions.md             # applyTo: "azure-pipelines*.yml,pipelines/**/*.yml"
```

- One path-scoped file per stack or area: `dbt`, `python`, `notebooks`, `pipelines`, `sql`, `terraform`, `powershell`, and so on.
  Split further (`dbt-marts.instructions.md`) only when a group of rules would be noise for the rest of the stack.
- Make `applyTo` as narrow as the real folders: `dbt/models/**/*.sql` rather than `**/*.sql` when other SQL exists elsewhere.
  Run the linter to confirm every glob matches files.
- Don't create a file for an area with no rules. An empty file is noise.
- The repo-wide file may legitimately be short, or even absent if every rule is area-specific.

## Template: `copilot-instructions.md`

```markdown
# <Repo name>: review rules for this repository

Project-wide rules for the <Project> project also apply; these add what is specific to this repo.
<One sentence on what the repo does and its main parts, e.g. "Python ingestion in src/ingest feeds dbt models in dbt/.">

## Architecture boundaries
- <rule>

## Domain rules
- <rule>

## Error handling
- <rule>

<!-- Maintained with the copilot-review-instructions skill. Manual edits are kept on re-run. Last run: YYYY-MM-DD -->
```

## Template: path-scoped file

````markdown
---
applyTo: "<glob>,<glob>"
---

# <Area> review rules

## <Heading>
- <rule>

```<lang>
// Avoid
...
// Prefer
...
```

<!-- Maintained with the copilot-review-instructions skill. Manual edits are kept on re-run. Last run: YYYY-MM-DD -->
````

Notes:
- The frontmatter must be the very first lines of a path-scoped file. The footer comment goes at the end so it doesn't
  use up the start of the file.
- Headings are suggestions; keep only the ones that have rules.
- No links, no "see X", no references to the project-level text. Copilot already has it.

## Update protocol (re-runs)

Existing instruction content belongs to the team. Someone may have hand-tuned it after a bad review. The rules:

1. **Read before you write.** Read every existing instruction file completely. Run
   `git log --format='%h %an %ad %s' --date=short -- <file>` and `git diff -- <file>` to see who changed it and whether there are uncommitted edits. Commits not titled
   `chore(copilot-review): …` are manual edits. Mention them to the user so they know what you are preserving.
2. **The Lockstep block is not yours.** Text between `<!-- lockstep:review-rules... -->` and
   `<!-- /lockstep:review-rules -->` is copied from AGENTS.md by `check_review_rules --write`. Don't edit, move or
   classify it; propose changes to it as AGENTS.md edits instead.
3. **Default is keep.** Every existing rule, heading, snippet and comment stays exactly as written, in its position.
   Don't reformat, reorder or reword existing text to match the template.
4. **Changes are proposals.** Classify each existing rule in the approval summary:
   - `keep`: the default; you don't need to list each one, just the count.
   - `change`: wording is vague, glob is wrong, or a path was renamed. Show old → new and why.
   - `remove`: only when the rule is now covered at project level, enforced by a linter, or refers to code that no longer exists.
     Show the evidence.
   - `move`: the rule is in the wrong scope (a dbt rule in the repo-wide file). Show from → to.
   Apply a `change`, `remove` or `move` only if the user approves that item.
5. **Add, don't regenerate.** Insert new rules under the matching existing heading, or a new heading at the end of the
   rules, using targeted edits. Never write a whole existing file from scratch.
6. **Update the footer date** (add the footer if the file has none).
7. **Diff check.** After writing, run `git diff --stat` and `git diff`. Every removed line must match an approved
   `change`/`remove`/`move`, or sit inside the Lockstep block. If not, restore it.

## Branch, commit and PR

- Branch: `chore/copilot-review-instructions` (add `-YYYYMMDD` if it already exists).
- Commit message: `chore(copilot-review): add|update repo review instructions`, with the rule count per file in the body.
- PR title: `Copilot review instructions for <repo>`.
- PR description (keep it short):

```markdown
Adds repo-specific Copilot code review rules on top of the <Project> project-level instructions.

| File | Applies to | Rules |
|---|---|---|
| .github/copilot-instructions.md | all files | N |
| .github/instructions/dbt.instructions.md | dbt/models/** | N |

**Sources:** reviewer pain points from <name/team>, plus conventions observed in <key paths>.
**Overlap with project rules:** none duplicated. <If any project rule is intentionally overridden: "Overrides project rule '<text>' for this repo because <reason>.">
**Takes effect:** after merge into <target branch> (Azure DevOps reads instructions from the target branch).
```

- Azure DevOps PR creation, if `az` with the `azure-devops` extension is available:
  `az repos pr create --source-branch <branch> --target-branch <default> --title "<title>" --description "<desc>" --draft false`.
  Otherwise give the user the URL:
  `https://dev.azure.com/<org>/<project>/_git/<repo>/pullrequestcreate?sourceRef=<branch>&targetRef=<default>`.
- GitHub: `gh pr create`, or the compare URL.
