# baseline

**What it does.** Brings existing code into Lockstep one area at a time. `hotspots.py` ranks folders by how often they
changed in the last year and shows which are already pinned. For the area you pick, the skill writes a baseline spec
(`kind: baseline`) that says what the code does today, with where each behaviour was seen, and pins every criterion
with a test that passes now. Existing tests can be adopted by adding only a criterion tag. Everything goes in one PR
from `baseline/<id>-<slug>` into main, and it changes no code. The flow is in
[docs/baseline-specs.md](../baseline-specs.md).

**When to reach for it.** Before you change an area that has no spec, when an area breaks often, or when a team first
adopts Lockstep in a repo that already has code. Not for new behaviour (`spec`) or wrong behaviour (`bugfix`).

**Common questions.**
- *Do we need a baseline for the whole repo?* No. Start with the area your next change touches, or the busiest
  unpinned one. Areas that never change can stay as they are.
- *What if the code does something wrong?* It doesn't become a criterion. Name it in the spec's scope and fix it
  through `bugfix`, or leave it as an open question for the author.
- *Why can't the baseline PR fix small things on the way?* A baseline records behaviour; a fix in the same PR would
  hide what changed. `check_spec_required` fails a baseline PR that touches code.
- *What happens when we later change pinned behaviour?* The change spec supersedes the baseline criterion, and a
  person updates the pinned test in a `[test-change]` PR.

**It's working if** the areas you change most show `pinned: yes` in `hotspots.py`, and change specs for those areas
supersede baseline criteria instead of surprising someone with a broken caller.
