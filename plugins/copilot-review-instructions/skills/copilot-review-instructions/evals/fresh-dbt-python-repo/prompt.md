---
tags: [skill-creator]
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our team gets Copilot code reviews on Azure DevOps and I want the sales-analytics repo (it's in ./repo) to get its own review instructions on top of our project-wide ones. The project-wide instructions are exported in ./project-instructions.md.

What reviewers keep correcting: dbt models outside staging reading source() directly, Python code that calls requests or reads os.environ instead of going through our client and settings, and new models added without primary-key tests in the yml. Copilot also keeps nagging about SQL keyword casing, which sqlfluff already checks.

I can't answer follow-up questions in this run, so treat those as my answers and treat your proposal as approved. Commit on a branch but don't push or open a PR. In your final reply, include the questions you would have asked me and the approval summary you would have shown.

Input files: repo/, project-instructions.md
