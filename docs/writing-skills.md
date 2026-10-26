# Writing Lockstep skills

How to write or change a skill in this repo. A skill is read by an agent with no other context, often in a busy
session, so every line has to earn its place.

## Shape

- **Frontmatter.** `name`, and a `description` that says what the skill does and when to use it, with the words people
  actually say. A skill people start on purpose (setup, retro, the `/lockstep` router) gets
  `disable-model-invocation: true` and a one-line description: it then costs no context until someone types it.
- **One job per skill.** If a skill needs "and then" in its name, it is two skills.
- **Numbered steps**, each with a heading that starts with a verb. Each step ends with how the agent knows it is done:
  a check that passes, an output to show, a question answered.
- **Under about 100 lines.** Put detail an agent needs only sometimes in a file next to `SKILL.md` and link it
  ([grilling.md](../plugins/lockstep-core/skills/spec/grilling.md) is the example). The agent reads it only when it
  gets there.

## Words

- **Point, don't paste.** Name the file, command or section to read (`specs/<id>-<slug>/spec.md`, section 5) rather
  than restating it. Restated rules drift from the original.
- **Say what to do, then what not to.** "Take expected values from the spec" works better than "don't compute expected
  values". Keep a prohibition for the few things that must never happen, and give the reason in a few words.
- **Facts for the agent, decisions for people.** The agent looks things up; it asks people only what it can't find.
- **Stop points are explicit.** PII, a test that looks wrong, a push: say "stop" and what to tell the user.
- **No no-ops.** Delete any line an agent would follow anyway ("be careful", "write clean code"). Each line should
  change what the agent does.
- British English, plain words, and invented examples only ("Test Person 001", `example.invalid`).

## Code next to a skill

- Scripts in `scripts/`, Python 3.11+ standard library only, runnable as `python3 scripts/<name>.py --root <repo>`.
- They gather facts and refuse unsafe states; judgement stays in `SKILL.md`.
- Tests in `tests/`, run from the repo root with pytest, using temporary git repos and invented data.
- Shared logic belongs in `lockstep_checks` (`core/src`), so hooks, CI and skills agree.

## Before you open the PR

- The skill is listed in the plugin's README row and in `.claude-plugin/marketplace.json` (CI checks this).
- Its page in [docs/skills/](skills/) is up to date.
- `ruff check`, `ruff format --check` and the tests pass.
