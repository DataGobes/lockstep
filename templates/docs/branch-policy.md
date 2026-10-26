# Branch policy for main

Lockstep's gates only bind when main's branch policies make them required. Set these in *Project settings → Repos →
Repositories → <repo> → Policies → main*, or run `scripts/ado/branch-policy.sh` after filling in its variables.

| Policy | Setting | Why |
|---|---|---|
| Minimum number of reviewers | 1; authors can't approve their own changes; reset votes on new pushes | The person who drove the agent owns the change; a different person approves it. |
| Comment resolution | Required | Copilot and human comments are answered, not ignored. |
| Merge types | Squash merge only | One commit per spec step on main keeps history and reverts simple. |
| Build validation | The PR pipeline (`azure-pipelines-pr.yml`), required, re-run when main updates | Tamper, traceability, size, Jira key, review rules and the quality gates. |
| Automatically included reviewers | A test reviewer group, required, for `/tests/*`, `*.unit_tests.yml`, `/evals/*`, `/.claude/*`, `/.lockstep/*`, `/AGENTS.md`, `/azure-pipelines*` | Locked tests and the rules agents work under change only with a second look. |
| GitHub Copilot code review | Added as an automatic reviewer (by hand: no CLI yet) | Advisory first review; it reads `.github/copilot-instructions.md` from main. |

**Feature branches.** The test PR merges into `feature/<id>-<slug>`, not main, so red tests never reach main; only
the green feature branch does. The tests lock when the test PR merges, so `feature/*` (prefix match) gets the same
reviewer count, comment resolution, build validation and test reviewer group for `/tests/*`, `*.unit_tests.yml` and
`/evals/*`. Merge types there: squash or merge commit, not rebase, which would hide the commit where the tests locked.

**Jira link.** Azure DevOps' linked-work-item policy covers Azure Boards only, so the PR pipeline's
`check_jira_key` is what ties a PR to its Jira issue: the title or branch needs a key like `MXAAI-123`.

**Prod.** Deploys to prod run only from main through the `<repo>-prod` environment in the deploy pipeline. Give that
environment one required approver group and untick *Allow approvers to approve their own runs*.
