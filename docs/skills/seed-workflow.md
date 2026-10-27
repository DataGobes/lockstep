# /seed-workflow (experimental)

**What it does.** Reads the repo (languages, test commands, CI, deploy tools, agent config, git history), asks the
team a few decisions, and proposes the smallest safe workflow: the fixed core plus only the practices that the repo's
risks or the team's own failures justify. Nothing is written until a person approves the proposal.

**When to reach for it.** A team starting with coding agents, or one for whom the full Lockstep flow is too much on
day one. It only runs when you type it.

**Common questions.**
- *Why so little?* Instructions an agent doesn't need make it worse. Each practice is added when a failure shows it
  is needed, with `/grow-workflow`.
- *Does it only pick from a fixed list?* It picks from the catalogue first. When nothing there covers something the
  team needs, it writes a practice for this repo, at most two at setup, marked as agent-written for you to review.
- *What can't we turn off?* The fixed core: criteria become tests, agents can't edit locked tests, and workflow changes
  are logged. It is what makes teams comparable.
- *Is it Lockstep?* Lockstep's skills are practices in its catalogue that a team grows into. See
  [the design](../seed/architecture.md).

**It's working if** the generated `AGENTS.md` block stays under 40 lines and every practice in it has a reason in
`.workflow/ledger.jsonl`.
