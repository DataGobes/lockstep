# /retro-capture

**What it does.** Gathers reverts, `[test-change]` PRs and fixes from git history for a period, adds what the team
reports, sorts it by cause, and turns the strongest cause into one change: a check for a mechanical mistake, a review
rule for a judgement call.

**When to reach for it.** At the end of a sprint or pilot, or after an incident. It only runs when you type it.

**Common questions.**
- *Why only one change?* One change a retro actually makes beats five it lists. The rest are kept for next time.
- *Hook blocks aren't in the report.* The hooks keep no log; tell it what you saw.

**It's working if** the same kind of mistake doesn't show up in two retros running.
