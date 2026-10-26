# bugfix

**What it does.** Fixes a bug without a full spec: a short bug report, a new regression test that fails for the bug's
reason, then the smallest fix, all in one PR on `bugfix/<KEY>-<slug>`. The PR check `check_spec_required` fails a
bugfix PR without the report or the new test. The lane follows SDTRD's Fast-Track Protocol.

**When to reach for it.** Something that is already meant to work doesn't. If the fix needs new behaviour, it's a
spec; if it needs a locked test to change, that's a `[test-change]` PR first.

**Common questions.**
- *Why can't I add the test to the existing test file?* Existing test files are locked; a new file proves the bug
  without weakening what's there.
- *What about dependency bumps and config?* Use a `chore/<slug>` branch: no spec, no bug report. The reviewer checks
  that it changes no behaviour.

**It's working if** each bug report names a criterion or says `none`, and its "why the tests missed it" line turns up
in the next retro.
