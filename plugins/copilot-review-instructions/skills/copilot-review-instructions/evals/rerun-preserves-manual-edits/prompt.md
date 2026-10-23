---
tags: [skill-creator]
max_turns: 60
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Copilot's reviews on sales-analytics (./repo) missed two things last sprint: a loader swallowed an error with `except Exception: pass`, and someone added an intermediate dbt model that reads from source() again. Can you update our Copilot review instructions so that gets caught? We set them up a while ago and a teammate tweaked them since. Project-wide instructions are in ./project-instructions.md.

I can't answer follow-up questions in this run, so treat your proposal as approved. Commit on a branch but don't push or open a PR. In your final reply, include the approval summary you would have shown me.

Input files: repo/, project-instructions.md
