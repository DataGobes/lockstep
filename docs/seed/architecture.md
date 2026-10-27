# Lockstep Seed: a workflow that starts small and grows from evidence

Status: prototype. Working name "Seed".

## The idea

One workflow does not fit every team. Seed is a short statement of principles ([SEED.md](../../plugins/lockstep-seed/SEED.md))
that an agent reads before it sets up a team's agentic workflow. The agent looks at the code base, asks the team a few
decisions, and proposes the **smallest** setup that is safe. Everything else is added later, one practice at a time,
when the team sees a failure that the practice prevents. Every addition and removal is logged with its reason.

Three rules keep it honest:

1. **Minimal start, human-curated.** The agent proposes; a person edits and approves. Research on AI-written context
   files shows they make agents worse, so the generated instructions block has a hard line budget, and holds only
   what the agent cannot find out itself (commands, irreversible risks).
2. **A small fixed core.** Three things every team gets, untailored, so teams can be compared and lessons carried
   across: criteria become tests, agents cannot edit locked tests, and every workflow change is logged.
3. **Measured.** Seeding records a baseline from git history (reverts, fix commits, test changes). Each later change
   cites the failure that caused it, so a team can see whether its workflow is paying for itself.

## Moving parts

```
                    ┌─────────────────────┐
  repo ──probe.py──▶│ profile  (facts)    │
                    └─────────┬───────────┘
  team ──interview─▶ answers (decisions)  │        catalogue layers
                              ▼                    plugin  < org  < repo
                    ┌─────────────────────┐        catalog/*.toml
                    │ compose.py plan     │◀────── practices = data
                    │  core + selected    │
                    └─────────┬───────────┘
                              ▼  person edits & approves
                    .workflow/workflow.toml   (desired state)
                              │
                 compose.py apply (idempotent render)
                              ▼
        AGENTS.md block · CLAUDE.md · .claude/settings.json · core hooks · CI check
                              │
                    .workflow/ledger.jsonl    (why each change happened)
                              ▲
  observed failure ──grow-workflow──▶ add / remove one practice
```

| Part | Kind | Job |
|---|---|---|
| `SEED.md` | prose, versioned | The principles and the fixed core. The only thing the agent must read first. |
| `catalog/*.toml` | data | One file per practice: the failure it prevents, the repo signals that make it relevant, when to add it, its cost, and what it renders. |
| `scripts/probe.py` | deterministic | Facts about the repo: languages, test runner, CI, agent tools, deploy tools, data and LLM stacks, team size from git. |
| `skills/seed-workflow` | agent | Probe, interview in rounds (Lockstep's grilling.md), propose, apply after a yes. |
| `scripts/compose.py` | deterministic | Picks practices by the start rule, writes `.workflow/workflow.toml`, renders files, appends to the ledger. |
| `core/` | code | The fixed core's hook and CI check, standard library only. |
| `skills/grow-workflow` | agent | Maps one observed failure to one practice (or a new repo-local one), adds or removes it, logs why. |
| `scripts/ledger.py` | deterministic | Baseline metrics, the change history, and practices due for review. |

## Why it scales

- **Practices are data.** Adding a practice is adding a TOML file; the engine does not change. The catalogue is layered
  (plugin, then an org folder, then `.workflow/practices/` in the repo), so a team can add its own without a fork and a
  good one can be promoted to the org layer.
- **Renderers are the only tool-specific code.** Claude Code and Copilot both read `AGENTS.md` and
  `.claude/settings.json` hooks, so one render serves both today. Another tool means another renderer, not a new catalogue.
- **Desired state, not scripts.** `workflow.toml` says what the team has; `apply` re-renders it, so re-running is safe
  and an upgrade of the catalogue re-renders every repo the same way.
- **The ledger is the cross-team dataset.** Same core, same event format: you can ask "which practices did teams add
  in month one, and did their revert rate drop?" across every repo.

## Relation to Lockstep

Lockstep is the opinionated full flow; Seed is the generator. In the prototype the core is implemented in a few small,
dependency-free files. Lockstep's skills appear in the catalogue as practices that a team grows into (`spec-first`,
`tests-first-red`, `baseline-pin`, ...). Later, the core can bind to `lockstep-checks` instead of its own copy once a
team adopts the Lockstep spec format. The same goes for SDTRD: its rules can be catalogue entries, which avoids a
"which framework wins" debate.

## Out of scope for the prototype

- Azure DevOps pipeline rendering beyond one PR check step.
- Automatic failure detection. The grow skill takes failures from people, the hook event log and git history.
- An org-level catalogue service. The layer exists as a folder path.
