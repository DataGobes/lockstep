---
name: grow-workflow
description: Change a seeded workflow by one practice, because of a failure the team saw or a practice that no longer earns its place, and log why.
disable-model-invocation: true
---

# Grow the workflow by one change

The workflow grows from what goes wrong, one change at a time, and shrinks when a practice stops paying. Read
[../../SEED.md](../../SEED.md) section 4 first. Paths are relative to this skill's folder.

## 1. Check where you are

- `.workflow/workflow.toml` must exist; if not, offer `/seed-workflow`.
- Clean working tree, then a new branch `chore/workflow-<YYYY-MM-DD>` from an up-to-date main.

## 2. Find the one change

Run `python3 ../../scripts/ledger.py report --root <repo>` and `python3 ../../scripts/ledger.py review --root <repo>`.
Then ask the person which applies, recommending the one with the most evidence:

- **A failure.** What happened, how often, and where (PR, commit, chat). Group repeats of the same cause; one cause is
  one change.
- **A review.** A practice `review` lists as due: has its failure been seen since it was added?

## 3. Match it to a practice

Read the `prevents` and `failures` fields of every file in `../../catalog/` and `.workflow/practices/`. Pick the
practice whose `prevents` names the cause, not the symptom. Prefer `kind = "mechanical"` when the mistake is always
wrong. Show the person the practice, its cost and the exact lines it would add to `AGENTS.md`.

No practice fits? Write one in `.workflow/practices/<id>.toml`, in the format of `../../catalog/README.md`, with one
`agents_md` line at most. Tell the person that if other teams write the same one, it belongs in the shared catalogue.

## 4. Apply it

```
python3 ../../scripts/compose.py add --root <repo> --practice <id> --reason "<the failure, in the person's words>" --evidence "<PR or commit>" --by "<their name>"
python3 ../../scripts/compose.py remove --root <repo> --practice <id> --reason "<not seen since YYYY-MM; hook never fired>" --by "<their name>"
```

The reason is required and lands in `.workflow/ledger.jsonl`. If it reports over budget, ask which practice to remove
first; never raise the budget.

## 5. Open the PR

Commit as `chore(workflow): <add|remove> <id>: <reason>`. The PR description gives the failure, the evidence and the
change. Ask before pushing. After merge, the change applies to every agent session that starts on main.
