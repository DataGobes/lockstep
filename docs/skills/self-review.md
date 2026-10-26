# self-review

**What it does.** Reviews the branch before its PR opens, in two separate passes: standards (repo rules, changed
tests, invented APIs, error masking, smells) and spec (each criterion met, missing or wrong, plus scope creep). Then
it fills in the PR description.

**When to reach for it.** At the end of implement, or any time you want a diff checked against its spec.

**Common questions.**
- *Why two passes?* So clean code can't hide a missing criterion, and the reverse.
- *Does it replace the human reviewer?* No. It removes what the reviewer would otherwise have to point out.

**It's working if** human review comments are about judgement, not about things a checklist would catch.
