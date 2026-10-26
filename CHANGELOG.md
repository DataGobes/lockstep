# Changelog

Versions of the Lockstep plugins and of `lockstep-checks`, which bootstrap vendors into product repos. Product repos
pin a tag (`--ref v0.1.0`); upgrading is running `/bootstrap-repo` again with a newer one.

To release: add the version's section here, run `python3 tools/check_release.py --set-version <version>`, merge, then
tag the merge commit `v<version>`.

## Unreleased

- **Warn mode:** `[enforcement]` in `lockstep.toml` sets each gate to `warn` (let it through, report that it would
  have been blocked, count it) or `enforce` (block). New repos start in warn; a repo without the table enforces, as
  before. CI tags each run `lockstep-would-block-<check>` or `lockstep-blocked-<check>`, and the hooks log to
  `.git/lockstep/hook-events.jsonl`, so the switch to enforce rests on numbers. The prod-deploy guard always blocks.
  Idea credited to Mohammed: Lockstep should encourage its use, not only block. See `docs/enforcement-modes.md`.
- **`check_spec_required`:** fails a PR that changes code without a spec at the right status. `chore/` branches need
  no spec; `bugfix/` and `hotfix/` branches need a bug report and a new regression test. Both lanes follow SDTRD.
- **Hooks find a newer Python:** the hook shim now looks for python3.14 down to python3.11 before `python3`, in the
  usual install folders too, and takes `LOCKSTEP_PYTHON`. On macOS `python3` is the system 3.9, which blocked every edit.
- **`bugfix` skill:** the light lane for bugs, with a bug report template in `specs/bug-reports/`.

## 0.1.0

First version for the pilot.

- **lockstep-core:** `/lockstep` next-step router, `/bootstrap-repo`, `spec` (interviews the author in rounds),
  `tests-first`, `implement` (vertical slices inside locked acceptance tests), `self-review` (separate standards and
  spec passes), `/retro-capture`.
- **lockstep-data:** `dbt-impact`.
- **lockstep-ai:** `eval-case`.
- **Shared checks and hooks:** PR size, Jira key, test tamper, AC traceability and review rules checks; hooks that
  block prod deploys and edits to locked tests.
- **Azure DevOps:** PR pipeline with the Lockstep checks and quality gates (Python, dbt Slim CI, bundle validate,
  evals), deploy pipeline (staging, then prod through an approved environment), branch policy script.
- **Templates:** AGENTS.md with Copilot review rules, CLAUDE.md, GLOSSARY.md, spec template, PR template.
