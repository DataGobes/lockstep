# copilot-skills

Team skills for working with GitHub Copilot code review. Every plugin in this repo installs in both
**Claude Code** and **GitHub Copilot CLI** from the same files.

| Plugin | What it does |
|---|---|
| [`copilot-review-instructions`](plugins/copilot-review-instructions/skills/copilot-review-instructions/SKILL.md) | Generates and maintains repo-specific Copilot code review rules (`.github/copilot-instructions.md` + path-scoped `.github/instructions/*.instructions.md`) on top of the project-wide rules. Works for Azure DevOps (Azure Repos) and GitHub. |

## Install

**Claude Code**

```
/plugin marketplace add DataGobes/copilot-skills
/plugin install copilot-review-instructions@datagobes-copilot-skills
```

**GitHub Copilot CLI**

```
copilot plugin marketplace add DataGobes/copilot-skills
copilot plugin install copilot-review-instructions@datagobes-copilot-skills
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
