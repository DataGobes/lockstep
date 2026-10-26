# Changelog

Versions of the Lockstep plugins and of `lockstep-checks`, which bootstrap vendors into product repos. Product repos
pin a tag (`--ref v0.1.0`); upgrading is running `/bootstrap-repo` again with a newer one.

To release: add the version's section here, run `python3 tools/check_release.py --set-version <version>`, merge, then
tag the merge commit `v<version>`.

## Unreleased

- **`check_spec_required`:** fails a PR that changes code without a spec at the right status. `chore/` branches need
  no spec; `bugfix/` and `hotfix/` branches need a bug report and a new regression test. Both lanes follow SDTRD.
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
