# copilot-review-instructions

**What it does.** Generates and maintains repo-specific Copilot code review rules in `.github/copilot-instructions.md`
and path-scoped `*.instructions.md` files, on top of the Lockstep rules that bootstrap copies in.

**When to reach for it.** After bootstrap, or when reviews keep missing a repo-specific problem.

**Common questions.**
- *Why not just AGENTS.md?* Copilot code review on Azure DevOps reads `.github/copilot-instructions.md`, not AGENTS.md.
- *When do new rules apply?* To PRs opened after the rules merge into the target branch.

**It's working if** Copilot's review comments cite your rules, and you stop repeating the same review comment.
