# Interviewing in rounds

Use this to empty a spec's open questions, or to settle unclear points before writing tests. The goal is a decision
on every question in as few round trips as possible, from a person who may only skim.

## Facts are yours, decisions are theirs

Before asking anything, look up what can be looked up: the code, the dbt project, the schemas, `GLOSSARY.md`, the
issue, earlier specs. Ask the person only for decisions: what the behaviour should be, which trade-off they want, a
value only the business knows. Never ask them a fact you could have found.

## One round at a time

1. List every open question. Mark which ones depend on another's answer.
2. Ask the **frontier** in one numbered message: every question whose prerequisites are settled. Not one at a time,
   and not questions that may disappear once an earlier one is answered.
3. Give each question a **recommended answer** with a one-line reason, and word it so that "yes" accepts the
   recommendation: "Late rows: drop rows older than 7 days? (Matches the nightly load window.)"
4. Accept short replies: "yes to all", "2: no, 14 days", "skip 3". A question they skip stays open.
5. Write the answers into the spec straight away (a criterion, a non-goal, a glossary entry), remove them from Open
   questions, and ask the next frontier. Stop when nothing is left or the person says stop.

## Keep it short

- At most about seven questions per round. More means the spec should be split; say so.
- No question about style, naming or anything the reviewer can decide in the PR.
- If an answer contradicts the issue, say so in the next round instead of silently picking one.
