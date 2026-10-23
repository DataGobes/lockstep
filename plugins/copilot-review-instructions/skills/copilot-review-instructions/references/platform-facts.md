# How Copilot code review reads instructions

Checked against Microsoft Learn (Azure Repos, doc dated 2026-08-03) and GitHub Docs on 2026-10-23.
Copilot code review for Azure Repos is in **preview**, so re-check these when behaviour surprises you.

## Azure DevOps (Azure Repos) vs GitHub

| | Azure DevOps | GitHub |
|---|---|---|
| Repo-wide file | `.github/copilot-instructions.md` **or** `.azuredevops/copilot-instructions.md` | `.github/copilot-instructions.md` |
| Path-scoped files | `.github/instructions/**/*.instructions.md` or `.azuredevops/instructions/**/*.instructions.md` | `.github/instructions/**/*.instructions.md` |
| Branch the instructions are read from | **Target branch only.** A PR that changes instructions is reviewed with the *old* ones. Changes take effect after merge. | **Head branch.** A PR that changes instructions is reviewed with the *new* ones. |
| Levels above the repo | Organization and Project settings (UI text boxes) | Organization settings (Business/Enterprise) |
| Precedence on conflict | Repository > Project > Organization | Repo and org are combined; no strict order is documented for code review |
| Agent files | Not documented | `AGENTS.md` (nearest wins), root `CLAUDE.md` / `GEMINI.md` are also read |
| Re-review after push | Not automatic; click **Request** next to GitHub Copilot again | Configurable |
| PR size limit | 100 files changed and 100 changes or fewer, no merge conflicts | — |
| Cost | GitHub AI credits billed to the linked Azure subscription per review | Copilot plan premium requests |

## Path-scoped file format (both platforms)

```markdown
---
applyTo: "dbt/models/**/*.sql,dbt/models/**/*.yml"
---
```

- `applyTo` is required. On Azure DevOps a path-scoped file without it is **skipped**.
- Multiple globs are comma-separated in one quoted string.
- Glob semantics: `*` matches within one folder, `**/` matches zero or more folders.
  `src/*.py` does not match `src/a/b.py`; `src/**/*.py` does.
- Rules apply only to **changed files** that match. A file that matches several `applyTo`s gets all of them, plus the repo-wide file.
- GitHub only: `excludeAgent: "code-review"` hides a file from code review (keeps it for the cloud agent). Never add it here.

## Choosing `.github/` vs `.azuredevops/`

Default to `.github/`: it works on both platforms, so the files survive a move to GitHub.
If the repo already has `.azuredevops/copilot-instructions.md` or `.azuredevops/instructions/`, keep using `.azuredevops/` and never create a second copy in `.github/`; with two copies it is undocumented which one wins.

## What the size and quality limits are

- GitHub's guidance: keep each file well under ~1,000 lines, start with 10–20 rules, and grow from what works.
  Long files get partially ignored.
- Older GitHub docs and several guides mention that only the first ~4,000 characters of a file are read. Current docs no longer state this, but put the highest-value rules first in each file anyway. It costs nothing.
- Copilot is non-deterministic: a rule that is followed 4 times out of 5 is working.

## Not supported (both platforms)

- Changing the look of comments (bold, emoji, comment format).
- Changing or adding to the PR overview / summary comment.
- Blocking, approving or rejecting a PR. Copilot always leaves a non-blocking **Comment** review.
- Following links. Copy the content in instead.
- Vague quality asks ("be accurate", "don't miss anything").

## Implications for the workflow

- **Azure DevOps:** merging the instruction PR is what turns the rules on. The PR that adds them cannot show their effect. Use the A/B setup in `ab-testing.md` to see the effect before or after merging.
- **Repo rules override project rules on Azure DevOps.** A repo rule that contradicts a project rule silently wins. Treat every such conflict as a decision for the user and record it in the PR description.
