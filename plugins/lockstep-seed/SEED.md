# Seed: principles for growing a team's agentic workflow

Read this before you set up or change a team's workflow. It is short on purpose: every line here changes what you do.

## 1. The fixed core

Every team gets these three, untailored. Do not drop or weaken them, and do not ask the team whether they want them.

| Id | Rule | Enforced by |
|---|---|---|
| `core-ac-tests` | Every acceptance criterion in a spec has at least one test that names its id. | `core/check_core.py` in CI |
| `core-locked-tests` | An agent never edits a test file listed in `.workflow/locks.toml`. A person changes it in a PR labelled `[test-change]`. | `core/protect_locked.py` hook, and the CI check |
| `core-ledger` | Every change to the workflow is one line in `.workflow/ledger.jsonl`, with its reason and evidence. | `compose.py`, the only writer |

The core is the same in every repo so teams can be compared and lessons can move between them.

## 2. Start small

At seeding time, add a practice only when one of these holds:

1. **Irreversible harm is reachable.** The probe found a way to cause it (a deploy CLI with a prod target, secrets in
   the tree, personal data in scope). Guards against things that cannot be undone come first.
2. **The agent cannot find it out.** Commands, a business term the code doesn't explain, a convention that only lives
   in people's heads. Nothing the agent can read from the repo goes into its instructions.
3. **The team already has evidence.** They name a failure that has happened, more than once, that the practice prevents.

Everything else waits. "It's best practice" is not evidence. When in doubt, leave it out and write it down as a
candidate in the proposal.

### When nothing in the catalogue fits

The catalogue is a set of examples, not a fence. If this team has a risk, a fact or a failure that passes the rule
above and no catalogue practice covers it, write a practice for it in `.workflow/practices/<id>.toml`, in the
catalogue's format, with `authored_by = "agent"`. Hold it to the same bar, and more:

- A new id. To change what a shipped practice says, decline it and write your own.
- `failures` names what goes wrong without it, in the team's words where you have them.
- At most two `AGENTS.md` lines; prefer a `deny` rule when the mistake is always wrong.
- At most **two** agent-written practices at seeding. The proposal marks them so a person reviews the wording.

Before writing one, check again that a catalogue practice doesn't already cover the cause; tailoring the commands or
the answers is usually enough.

## 3. Budgets

- The generated block in `AGENTS.md` stays under **40 lines**. If a practice would push it over, the proposal must
  remove something first.
- At most **five** non-core practices at seeding, of which at most two are agent-written. More means the team is
  guessing.
- Never generate long prose for the agent. One line per rule, imperative, with the reason in a few words.

## 4. Grow from observed failures

- One failure, one change. Name the failure, find the practice that prevents it, add it, log it.
- Prefer a **mechanical** fix (hook, check, setting) when the mistake is always wrong; an instruction line only when it
  needs judgement.
- No practice in the catalogue fits? Write a repo-local one in `.workflow/practices/`. If three teams write the same
  one, it belongs in the shared catalogue.
- Review practices regularly. A practice whose failure has not been seen and whose hook has not fired for 90 days is a
  candidate for removal. Removing is logged the same way as adding.

## 5. People decide

You look things up; people decide. Ask only what you could not find, in rounds, with a recommended answer for each
question. A person approves the proposal before anything is written, and every later change goes through a PR.
