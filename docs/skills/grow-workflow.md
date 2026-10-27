# /grow-workflow (experimental)

**What it does.** Takes one failure the team saw with an agent, or a practice that is due for review, and makes one
change: adds the catalogue practice that prevents it, or removes one that no longer earns its place. The reason and
evidence go into `.workflow/ledger.jsonl`, and the change goes out as a PR.

**When to reach for it.** After an agent got something wrong in a way you don't want again, or at a retro. It only
runs when you type it.

**Common questions.**
- *Nothing in the catalogue fits.* It writes a repo-local practice in `.workflow/practices/`. If several teams write
  the same one, promote it to the shared catalogue.
- *How do we know it helps?* `ledger.py baseline` puts the git figures at seeding next to the last 90 days.

**It's working if** each practice in the workflow can point to a failure, and practices whose failure stopped showing
up get removed.
