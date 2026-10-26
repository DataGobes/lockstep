# spec

**What it does.** Turns a Jira issue into a draft spec: problem, non-goals, numbered acceptance criteria (EARS, or Given/When/Then if the repo or you prefer it), a test
plan, risks. It then interviews you in short rounds, each question with a recommended answer, until Open questions is
empty, and opens the spec PR.

**When to reach for it.** At the start of any piece of work, before code. Say "spec MXAAI-123" or "write a spec".

**Common questions.**
- *EARS or Given/When/Then?* Either. `[specs] ac_format` in `lockstep.toml` can require one for the whole repo
  (`ears` or `given-when-then`); the default `any` accepts both and checks that Given/When/Then steps are in order.
- *Why does it stop when I say the work touches personal data?* PII work goes through the company Copilot. Run the same
  skill there.
- *Can I answer "yes to all"?* Yes. Each question is worded so "yes" accepts the recommendation.
- *Where do business definitions go?* `GLOSSARY.md`, in the same PR.

**It's working if** the reviewer approves the spec without a round of "what does this mean?" comments.
