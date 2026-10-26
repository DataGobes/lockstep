---
name: lockstep
description: Show where each spec is in the Lockstep flow and the next step to take.
disable-model-invocation: true
---

# Where am I, and what's next?

The one command to remember. Run it in a Lockstep repo at any point; it reads each spec's `status.yml` and the
branches that exist for it, and names the next skill.

## 1. Read the state

Run `git fetch origin` first, then:

```
python3 scripts/next_step.py --root <repo>
```

(Paths are relative to this skill's folder; it needs Python 3.11+ and git.) It prints one row per spec: status,
branches, the next step and the skill for it, and, when the current branch belongs to a spec, the step for that spec.
If the repo has no `.lockstep/`, it says to run `/bootstrap-repo` first.

## 2. Tell the user

Lead with the step for the current branch, if there is one. Then list the other specs that need something, briefly,
most advanced first. Skip specs that are done unless the user asks.

| Status | Next | Skill |
|---|---|---|
| no specs yet | start one from a Jira issue | `/spec` |
| draft | finish the spec and its interview, open the spec PR | `/spec` |
| approved | write the failing tests, open the test PR into the feature branch | `/tests-first` |
| tests-locked on the feature branch | implement against the locked tests | `/implement` |
| tests-locked, commits after the lock | finish, then review and open the PR into main | `/self-review` |
| implemented | done; lessons go to the next retro | `/retro-capture` |
| a bug in existing behaviour | report, red regression test, fix | `bugfix` |
| baseline spec, draft or approved | describe what the code does today, pin it with passing tests | `baseline` |
| existing code with no spec, about to change | pin it first | `baseline` |

A spec with `pii: yes` is worked on in the company Copilot only; say so if you are Claude.

## 3. Offer the next step

Ask whether to start the named skill now. Don't start it without a yes: the user may want a different spec.
