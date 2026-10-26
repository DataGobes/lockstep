# spec

**What it does.** Turns a Jira issue into a draft spec: problem, non-goals, numbered EARS acceptance criteria, a test
plan, risks. It then interviews you in short rounds, each question with a recommended answer, until Open questions is
empty, and opens the spec PR.

**When to reach for it.** At the start of any piece of work, before code. Say "spec MXAAI-123" or "write a spec".

**Common questions.**
- *Why does it stop when I say the work touches personal data?* PII work goes through the company Copilot. Run the same
  skill there.
- *Can I answer "yes to all"?* Yes. Each question is worded so "yes" accepts the recommendation.
- *Where do business definitions go?* `GLOSSARY.md`, in the same PR.

**It's working if** the reviewer approves the spec without a round of "what does this mean?" comments.
