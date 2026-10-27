---
name: seed-workflow
description: Set up the smallest safe agentic workflow for this team and repo, from its code, tools and a short interview.
disable-model-invocation: true
---

# Seed a workflow for this team

You set up a team's agentic workflow from scratch: the fixed core, plus only the practices this repo and team need
today. Read [../../SEED.md](../../SEED.md) first; it is the rule book for every choice below. Paths are relative to
this skill's folder. The scripts need Python 3.11+ and git.

## 1. Check where you are

- Root of a git repo, clean working tree. If not clean, ask first; don't stash.
- If `.workflow/workflow.toml` exists, the repo is already seeded: stop and offer `/grow-workflow`.
- Work on a new branch `chore/seed-workflow`.

## 2. Gather the facts

```
python3 ../../scripts/probe.py --root <repo>
```

Read what it prints, then the README and any existing `AGENTS.md`, `CLAUDE.md` or `.github/copilot-instructions.md`.
Note what the probe got wrong (a test command that isn't the one CI runs, say) to correct in step 4.

## 3. Interview the team

Ask only what you could not find. Use the rounds in [interview.md](interview.md): one message, every question with a
recommended answer, short replies accepted. The answers that matter most are the **failures they have already
seen** with agents: each one can justify a practice; "best practice" can't.

Write the answers to `answers.toml` in the scratch folder (not the repo), in the format `interview.md` shows.

## 4. Propose

```
python3 ../../scripts/compose.py plan --root <repo> --answers <answers.toml>
```

If the interview turned up a risk, fact or failure that passes the start rule and no catalogue practice covers it,
write a practice for it first, as SEED.md section 2 ("When nothing in the catalogue fits") describes, in
`.workflow/practices/<id>.toml` with `authored_by = "agent"`, and re-run `plan`.

Show the person the proposal it prints: the practices to start with and why, the ones left for later, and the exact
`AGENTS.md` block. Then ask them to edit it: drop a practice (add it to `[[decline]]` with their reason), add one
they have evidence for, or correct a command. Point out each practice marked agent-written and ask them to read its
lines word for word. Re-run `plan` after each change. If it reports over budget, remove
something; never raise the budget.

Stop until the person says yes to the proposal.

## 5. Apply

```
python3 ../../scripts/compose.py apply --root <repo> --answers <answers.toml> --by "<their name>"
```

It writes `.workflow/` (desired state, ledger, core hook and check), the `AGENTS.md` block, `CLAUDE.md`,
`.claude/settings.json` and a CI check for the pipelines it found. Handle every `merge:` and `todo:` line it prints
with the person. If the probe's commands were wrong, fix them in `.workflow/workflow.toml` under `[commands]` and run
`compose.py render`.

## 6. Prove the core works

- `echo '{"tool_name":"Write","tool_input":{"file_path":".workflow/locks.toml"}}' | python3 .workflow/core/protect_locked.py`
  must exit 2. With `"file_path":"README.md"` it must exit 0.
- `git fetch origin && python3 .workflow/core/check_core.py --base origin/main` must pass.

## 7. Commit and hand over

Commit as `chore: seed the agentic workflow`. Ask before pushing. Then tell the person:

- What they got, in three lines, and what was left out on purpose.
- How it grows: when an agent fails in a way they don't want again, run `/grow-workflow`.
- One thing only they can do: add the CI check as a required check on main.
