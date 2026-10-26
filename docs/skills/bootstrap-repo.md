# /bootstrap-repo

**What it does.** Sets a product repo up for Lockstep, or upgrades it: copies the shared checks, hooks and pipeline
templates into `.lockstep/`, writes `lockstep.toml`, AGENTS.md, CLAUDE.md, the glossary, the PR template and the
pipelines, merges with files the repo already has, and lists the Azure DevOps settings a person must make.

**When to reach for it.** Once per repo, and again to upgrade to a newer Lockstep version. It only runs when you type it.

**Common questions.**
- *Will it overwrite my AGENTS.md?* No. Files the repo owns are created when missing and otherwise merged with you.
- *No GitHub access from my machine?* Point it at a local Lockstep checkout with `--source`.
- *Why must I run the branch-policy script myself?* It changes the repo's settings, which an agent never does.

**It's working if** the checks pass on a fresh branch and the deploy hook blocks `databricks bundle deploy -t prod`.
