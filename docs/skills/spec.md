# spec

**What it does.** Turns a Jira issue into a draft spec: problem, non-goals, numbered acceptance criteria (EARS, or Given/When/Then if the repo or you prefer it), a test
plan, risks. It then interviews you in short rounds, each question with a recommended answer, until Open questions is
empty. Before the PR, a reader with none of the conversation checks the spec for terms, untestable criteria and
contradictions. Then it opens the spec PR.

**When to reach for it.** At the start of any piece of work, before code. Say "spec MXAAI-123" or "write a spec".

**Common questions.**
- *What about big pieces of work?* Ask for the research and design step, or let the repo require it above a number of
  criteria (`[specs] design_from_criteria`). The spec then also gets `research.md` (options and a decision, before
  the criteria) and `design.md` (interfaces, data flow, test seams, after them), reviewed in the same spec PR.
- *EARS or Given/When/Then?* Either. `[specs] ac_format` in `lockstep.toml` can require one for the whole repo
  (`ears` or `given-when-then`); the default `any` accepts both and checks that Given/When/Then steps are in order.
- *Why does it stop when I say the work touches personal data?* PII work goes through the company Copilot. Run the same
  skill there.
- *Can I answer "yes to all"?* Yes. Each question is worded so "yes" accepts the recommendation.
- *Where do business definitions go?* `GLOSSARY.md`, in the same PR.

**It's working if** the reviewer approves the spec without a round of "what does this mean?" comments.
