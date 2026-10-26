# Changelog

Versions of the Lockstep plugins and of `lockstep-checks`, which bootstrap vendors into product repos. Product repos
pin a tag (`--ref v0.1.0`); upgrading is running `/bootstrap-repo` again with a newer one.

To release: add the version's section here, run `python3 tools/check_release.py --set-version <version>`, merge, then
tag the merge commit `v<version>`.

## Unreleased

- **Given/When/Then criteria:** an acceptance criterion can be a title with GIVEN / WHEN / THEN steps under it, as
  well as one EARS sentence. `[specs] ac_format` in `lockstep.toml` (`any`, `ears` or `given-when-then`) sets what
  `check_ac_traceability` accepts; the default `any` accepts both and checks the steps' order. The spec template, the
  `spec` and `tests-first` skills and the self-review spec pass show the steps. Credited to SDTRD's behavioural
  scenarios.
- **Mutation report:** `lockstep_checks.mutation_report` and the `mutation-report.yml` pipeline template run mutmut
  on the modules a PR changed and show the mutation score, with each mutant the tests missed annotated at its line.
  Report only: it never fails the PR. A new `mutation` job in the PR pipeline template; delete it to skip it.
  Credited to SDTRD, whose rail requires every mutant killed. See `docs/mutation-testing.md`.
- **Jira optional per repo:** `[jira] required = false` in `lockstep.toml` lets a team without Jira approve
  specs and open PRs without an issue key. A key that is given is still checked. The default stays `true`.
- **Build only what a criterion needs:** a YAGNI non-negotiable in the AGENTS.md template, the scope-creep review
  rule and the self-review scope pass now cover speculative code (unused helpers, abstractions, config flags, new
  dependencies). Credited to SDTRD.
- **Superseding criteria across specs:** a struck criterion can point to a later spec (`~~AC-003~~ superseded by
  0057/AC-001`). `check_ac_traceability` fails a pointer to a missing or inactive criterion, and its warning on tests
  that still name the old criterion says where to point them. The spec template and the `spec` skill explain how.

## 0.2.0

Ready for the pilot: gates start in warn mode, and red tests never reach main. Both follow points Mohammed
raised.

- **Red tests stay off main:** the test PR now merges into `feature/<id>-<slug>` instead of main, and only the green
  implementation merges into main (with squash merge, main's history never has a red commit). The tests lock at the
  commit where the test PR merged into the feature branch: `protect_tests` and `check_test_tamper` protect them from
  there, review fixes inside the test PR stay allowed, and the commit order proves the tests came first. `tests-first`,
  `implement`, `/lockstep` and the branch policy script (now also for `feature/*`) follow the new flow; specs locked on
  main under 0.1 keep working. Rule credited to Mohammed (from SDTRD): no broken code on main.
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
