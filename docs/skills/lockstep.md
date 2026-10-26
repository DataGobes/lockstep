# /lockstep

**What it does.** Reads each spec's `status.yml` and the `spec/`, `test/` and `feature/` branches for it, and tells you
where each spec is and which skill comes next.

**When to reach for it.** Whenever you're unsure what to do next, or come back to a repo after a while. It only runs
when you type `/lockstep`.

**Common questions.**
- *Why does it show a status my branch has already changed?* It counts what is merged: on the spec's feature branch
  if there is one (the test PR merges there), else on main. Your branch's change counts once its PR merges.
- *A spec shows `invalid`.* Its `status.yml` has a mistake; the message says which line.

**It's working if** you never have to remember the order of the skills.
