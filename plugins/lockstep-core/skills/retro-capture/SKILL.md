---
name: retro-capture
description: Run a short retro over a period of work and turn its evidence into one change to the repo's rules, as a PR.
disable-model-invocation: true
---

# Capture one lesson from a retro

A retro is worth something only when it changes how the next piece of work runs. Your output is **one** concrete
change to AGENTS.md, a review rule, `lockstep.toml`, the spec template or a skill, opened as a PR. Not a list.

Paths below are relative to this skill's folder. `scripts/retro.py` needs Python 3.11+ and git.

## 1. Agree the period

Ask for the date range (default: the last two weeks) and run `git fetch origin` first.

## 2. Gather the evidence

```
python3 scripts/retro.py --root <repo> --since <YYYY-MM-DD> [--until <YYYY-MM-DD>]
```

It lists the commits on main in the range and sorts them into **revert**, **test-change** and **fix**, with the spec
id when the subject names one. For each entry, read the PR or commit to learn what happened. Then ask the team, in one
message:
- Which agent actions did a hook block (a deploy, a test edit)? The hooks keep no log, so this comes from people.
- Where did an agent go wrong or need rescuing: an invented API, scope creep, a test it wanted to bend?
- Which spec criteria turned out vague or untestable?

Never copy personal data, customer data or names from PRs or chat into the notes; describe the pattern instead.

## 3. Sort the evidence

Group the evidence by cause, not by symptom: a revert and two fixes on the same spec usually share one cause. Put each
group in one category, most severe first, and show the user the groups with the evidence behind each:

| Category | The agent or the team... |
|---|---|
| Automated checks | made a mistake a check, hook or test could have caught |
| Coding standards | wrote code a reviewer had to correct for style, structure or a repo convention |
| Spec quality | worked from a criterion that was vague, untestable or missing an edge case |
| Steering files | didn't know a rule, because AGENTS.md or a skill doesn't say it or says it badly |
| Navigation | looked in the wrong place, or couldn't find the code, model or command it needed |
| Information access | lacked something it needed: docs, lineage, a pinned version, a connector |
| Tool economy | spent many steps on something one command or script would do |
| No-op | nothing to change: a one-off, or already fixed |

## 4. Pick one change

Agree with the user on the single change with the most evidence behind it. Decide its kind first:

- A **mechanical** mistake (always wrong, recognisable without judgement) becomes a deterministic check: a
  `lockstep.toml` setting, a hook, or an issue on the Lockstep repo for a new check in `lockstep-checks`.
- A **judgement call** (right or wrong depending on context) becomes a review rule in the `lockstep:review-rules`
  block of AGENTS.md, or a line elsewhere in AGENTS.md.
- A spec-quality cause becomes a prompt or example for `specs/_template/spec.md` or the spec skill, as an issue on
  the Lockstep repo, since the template is Lockstep-owned.

Write the rest down as candidates for the next retro, in the PR description, not as more changes.

## 5. Open the PR

- Branch `chore/retro-<YYYY-MM-DD>` from an up-to-date main. Commit as `<KEY> Retro <date>: <the change>`.
- If you changed the review rules block, run `PYTHONPATH=.lockstep/src python3 -m lockstep_checks.check_review_rules
  --write` so `.github/copilot-instructions.md` matches.
- The PR description has: the period, the evidence table (kind, commit, one line), the cause, the change, and the
  candidates left for next time. Ask before pushing.
