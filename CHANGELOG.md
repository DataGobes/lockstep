# Changelog

Versions of the Lockstep plugins and of `lockstep-checks`, which bootstrap vendors into product repos. Product repos
pin a tag (`--ref v0.1.0`); upgrading is running `/bootstrap-repo` again with a newer one.

To release: add the version's section here, run `python3 tools/check_release.py --set-version <version>`, merge, then
tag the merge commit `v<version>`.

## Unreleased

## 0.5.3

- **Fix: the hooks took the branch from CI variables.** `guard_bash`, `protect_tests` and the hook event log asked
  for the PR branch a CI job's variables name (`GITHUB_HEAD_REF`, `SYSTEM_PULLREQUEST_SOURCEBRANCH`) before asking
  git, so an agent running inside CI saw every checkout as the PR branch: a reset of a `main` checkout was allowed,
  and a tests-locked spec's tests were unlocked. The hooks now judge the branch git has checked out; the checks still
  read CI first ([bug report](specs/bug-reports/hooks-branch-from-git.md)).
- **Fix: `guard_bash` trusted git options hidden behind a `$`.** Before a history rewrite, a git command with a word
  containing `$` (`$'--upload-pack=...'`, `$OPT`) is no longer trusted, since only the shell knows what it becomes. A
  `$` in the rewrite's own arguments (`-m "$MSG"`) stays allowed
  ([bug report](specs/bug-reports/guard-bash-dollar-words.md)).

## 0.5.2

- **Fix: `guard_bash` missed abbreviated and bundled git options before a history rewrite.** git takes any
  unambiguous prefix of a long option (`--upload-p`) and bundles short ones (`-qu`), so 0.5.1's list of options to
  reject fell short. A read-only git command before a rewrite now stays trusted only when all its options are on a
  short list (`-q`, `-s`, `-b`, `--short`, `--stat`, `--oneline`, `--cached`, `-A`, `-p`, `-<n>` and a few more), and
  a `fetch` with a `src:dst` refspec isn't trusted ([bug report](specs/bug-reports/guard-bash-git-options.md)).

## 0.5.1

Fixes to the agent hooks, from reviewing what they let through.

- **Fix: `protect_tests` missed a locked test the base branch didn't have yet.** A test that exists at an
  `implemented` spec's `locked_at_commit` is now locked on every branch, also when `origin/main` lacks it or the lock
  sits on a merge's second parent ([bug report](specs/bug-reports/protect-tests-locked-at-commit.md)).
- **Fix: `guard_bash` judged a history rewrite by the session's folder.** It now follows a plain `cd <folder> &&` and
  `git -C` to the checkout the command runs in, and blocks a rewrite whose checkout it can't work out, from any
  branch. Before a rewrite, only `cd` and the git subcommands `status`, `log`, `diff`, `show`, `fetch` and `add` are
  trusted, and only without options that run a command or write a file (`--upload-pack`, `--output`, `--ext-diff`,
  `--textconv`). So `ruff format . && git commit --amend` is now blocked: run the rewrite as its own command
  ([bug reports](specs/bug-reports/guard-bash-cd.md), [2](specs/bug-reports/guard-bash-unfollowed.md),
  [3](specs/bug-reports/guard-bash-git-allowlist.md), [4](specs/bug-reports/guard-bash-git-arguments.md)).
- README: the hooks are an early warning that a script or an unknown tool gets past; the PR pipeline's checks are the
  gate, so make the Lockstep pipeline a required check.

## 0.5.0

Lockstep on GitHub as well as Azure DevOps, SDTRD repos read as they are, and a fix for the Lockstep summary.

- `lockstep-checks` runs in GitHub Actions as well as Azure Pipelines: the checks read the PR's target branch, source
  branch and head commit from either system's variables (one module, `ci.py`), and findings show as GitHub annotations.
  New workflow template `templates/github-actions-pr.yml`. First step towards running Lockstep on SDTRD repos.
- SDTRD format: `[specs] format = "sdtrd"` reads an SDTRD repo as it is: feature folders in `specs/features/` and
  `specs/archive/`, REQ-/NFR- keys named by tests (`@REQ-AUTH-1`), status from ticked Review Gate boxes (Gate 2, 4, 6,
  B1). New `[lanes] feature` setting (default `["feature/"]`). Profile `templates/sdtrd/lockstep.toml`, guide
  `docs/sdtrd.md`.
- `examples/sdtrd-demo/demo.py`: builds a project with SDTRD's `sdtrd init`, adds Lockstep with the SDTRD profile and
  runs the checks on five PRs (four blocked for different reasons, one clean).
- `/bootstrap-repo` trims the PR pipeline to the chosen tracks (spec 0003): `--tracks data` drops the `evals` job,
  `--tracks ai` drops `dbt` and `bundle`, so there are no jobs left to delete by hand.
- **Fix: the Lockstep summary lost the quality and mutation evidence.** The PR templates published their evidence
  as `lockstep-evidence-$(System.JobName)`, which Azure DevOps resolved to `__default` in more than one job, so the
  second upload failed and the summary showed tests and coverage as not measured. Each template now uses a fixed
  name: `lockstep-evidence-checks`, `-quality` and `-mutation`
  ([bug report](specs/bug-reports/evidence-artifact-names.md)). Upgrading: run `/bootstrap-repo` with the new tag.

## 0.4.0

Ready for the first pilot: a trust summary on every PR, baseline specs for existing code, team rules, one spec-and-tests PR
by default, and the fixes from a full pre-pilot review.

- **Lockstep summary on every PR** (spec 0001). A summary stage after the PR jobs posts one comment on the Azure
  DevOps PR and replaces it on later runs: each criterion with its tests and their results in this run, the commit
  where the tests locked and whether a protected file changed since, the test-tamper check, changed-line coverage and
  the mutation score. Anything a job didn't measure says "not measured", never clean, and the PR description is never
  read. Each job writes `lockstep-evidence/<producer>.json` (`lockstep_checks.evidence`); `python -m
  lockstep_checks.trust_summary` prints the same summary locally, `--json` for tools. The PR template drops its
  hand-filled AC table, and the pytest plugin the red report uses moved into core as
  `lockstep_checks.pytest_evidence`. Upgrading: the PR pipeline template now has a checks stage and a summary stage,
  and the build service needs *Contribute to pull requests* ([docs](docs/trust-summary.md)).
- **Fixes from a full review before the first pilot.**
  - The test lock survives merging main into the feature branch. Before, the lock commit vanished from `git log`'s
    simplified history, so the hook and `check_test_tamper` let the spec's own tests change.
  - Test PRs can pass the feature branch's build validation. In a PR into a feature branch, the test files that
    branch adds (`lockstep_checks.red_phase`) run as a report and coverage is a warning; the PR into main runs
    everything.
  - The edit hooks find the repo from each file's folder, so they guard the implement worktree in `../<repo>-<id>`
    even when the agent's session started in the main checkout.
  - `protect_tests` also stops shell commands that write, move or delete a locked test (`sed -i`, `>`, `rm`, `mv`,
    `cp`, `git checkout --`). The settings template registers it for Bash and PowerShell.
  - The PR into main sets `status: implemented`, and `check_spec_required` fails one that doesn't (a warning
    locally), so `/lockstep` no longer offers to implement a merged spec again.
  - The checks read `lockstep.toml` from the target branch, so a PR cannot loosen the rules it is checked by, and
    the branch policy puts `lockstep.toml` under the test reviewer group.
  - `new_spec.py` skips ids still on `spec/`, `test/`, `feature/` and `baseline/` branches, so two specs in flight
    never share an id.
  - A spec that came in its test PR works end to end: `start_implement.py` reads the spec from the feature branch,
    and `/lockstep` reports that PR as a test PR.
  - `/lockstep` warns when the repo's vendored core is older than the plugin; `lockstep_checks.__version__` and the
    template's `core_version` are kept in step by `check_release.py`.
  - Setup and upgrade PRs pass their own checks: `.lockstep/` doesn't count towards the PR size or the tamper scan.
    Repos keep their own `[pr_size] ignore`; add `".lockstep/**"` to it.
  - The hooks write no `__pycache__`, and bootstrap adds `.lockstep/.gitignore`.
  - A broken `lockstep.toml` is named as such, and an edit to it is allowed so it can be fixed; `/lockstep` explains
    it instead of printing a traceback.
  - Specs: a wrapped EARS line that starts with "when" or "and" is no longer read as a Given/When/Then step, and
    "- None" under Open questions is not an open question.
  - `# noqa` and `type: ignore` in product code are warnings for the reviewer; in test files they still fail.
  - `[test-change]` PRs use `test/<id>-<slug>-<what>`, which `check_spec_required` accepts, into the feature branch
    or, for an implemented spec, into main.
  - Smaller: `bootstrap.py --no-jira`, hotspots skip Lockstep's own setup files, AGENTS.md lists every check.

- **Safety scan of shipped files:** `tools/check_release.py` now also runs `tools/safety_scan.py` over everything
  Lockstep ships (plugins, `core/src`, `core/hooks`, `core/pipelines`, templates). It fails on likely secrets, network
  access outside an allowlist (`ado_pr_title.py` reads the PR title from Azure DevOps), risky calls (`shell=True`,
  `os.system`, `eval`/`exec`, `pickle`) and hidden or bidi unicode. Tests and evals are skipped. Inspired by Tessl's
  skill security checks.
- **Property tests for invariant criteria:** `tests-first` proposes a Hypothesis property test next to the example
  tests for criteria that hold for every input (never negative, one row per key, idempotent, round trip), when the
  repo pins Hypothesis. Settings keep locked property tests deterministic (`derandomize=True`), and found cases are
  pinned with `@example`. See `tests-first/property-tests.md`. After Kiro's property-based testing.
- **One spec-and-tests PR by default:** a new spec goes into its test PR (`test/<id>-` into `feature/<id>-`), so a
  change takes two PRs instead of three: the reviewer agrees the criteria and checks the failing tests against them
  in one sitting, then the implementation PR goes into main. The tests still lock when that PR merges, the red
  phase is still proven, and red tests still stay off main. A large or risky spec gets a spec PR of its own first,
  by the lines in `[specs]`: more criteria than `spec_pr_above_criteria` (8 by default; 0 restores a spec PR for
  every spec), or a trait in `spec_pr_for` (by default `design`, the research and design step, and `contract`, the
  new `contract: yes` in `status.yml` for a change to an enforced data contract or an interface others use, and `pii`,
  for personal data). `check_spec_required` fails a test PR that brings a spec over a line, and the new `lockstep_checks.spec_pr
  <id>` tells the `spec` skill which way to go. `new_spec.py` now starts the spec on `test/<id>-<slug>` and takes
  `--contract`. Replaces the unreleased opt-in quick lane (`quick_max_criteria`). After Kiro's Quick Spec and BMAD's
  scale-adaptive tracks.
- **Team rules:** `[[rules]]` in `lockstep.toml` lets a team add its own rules without code: a regex that must not
  appear in added code (`on = "content"`, optionally only under `paths`) or in an agent's shell command
  (`on = "command"`). The new `team_rules` hook stops the agent, and the new `check_team_rules` PR check fails added
  lines that break a content rule, so both apply the same rule. Every key is validated; `[enforcement] team_rules`
  sets warn or enforce. The settings template registers the hook and the PR pipeline runs the check. After Probity.
- **Spec analysis:** `check_ac_traceability` warns about criteria that are hard to test, in specs still in draft or
  approved: should/may/might, vague words (fast, appropriate, and/or, several, ...), two SHALLs in one criterion, a
  non-functional criterion without a number, and criteria that repeat each other. Warnings only; the `spec` skill
  fixes them or says why they stay. After Kiro's requirements analysis.
- **Fresh eyes and evidence:** the `spec` skill has a reader with none of the conversation check the spec for
  undefined terms, untestable criteria and contradictions before the spec PR (after Google's Elephant-Goldfish
  model). `implement` gives long plans a fresh context per slice with a review between slices, and no skill reports a
  pass it didn't just run and show (after superpowers' subagent-driven development and verification before
  completion). `bugfix` traces the root cause to `path:line` before fixing, and stops after three failed fixes (after
  superpowers' systematic debugging).
- **Baseline specs for existing code:** a spec with `kind: baseline` in `status.yml` describes what an area of the
  code does today and pins it with tests that pass today, in one PR from `baseline/<id>-<slug>` into main. Its
  lifecycle is draft, approved, implemented (never tests-locked). `check_spec_required` holds a baseline PR to tests,
  specs and docs only, and to `status: implemented` once it adds tests; a baseline's id can't be used on `feature/`
  or `test/`. On a `baseline/` branch `check_test_tamper` lets an existing test gain criterion tags
  (`@pytest.mark.ac(...)`, `meta: {ac: ...}`) as long as nothing else in it changes. New `baseline` skill with
  `hotspots.py`, which ranks folders by recent commits and shows which are already pinned; `new_spec.py --baseline`;
  a baseline spec template in `specs/_template/baseline/`; `/lockstep` routes baseline specs; `baseline` PR type.
  The default `branch_pattern` now includes `baseline`; a repo that sets its own adds it. Inspired by OpenSpec,
  BMAD and Agent OS. See `docs/baseline-specs.md`.

## 0.3.0

More of SDTRD's strengths, ported with credit, and Jira made optional. Everything that changes the workflow is off
until a repo turns it on in `lockstep.toml`; the mutation report only reports.

- **Parallel streams:** the `implement` skill can run independent slices in parallel, one agent per git worktree.
  `scripts/streams.py` creates a branch `feature/<id>-<slug>--<stream>` and a worktree per stream from the feature
  branch, lists them, and removes a stream once its PR into the feature branch has merged (squash merges included).
  Shared contracts come first; the hooks and checks keep the locked tests locked in every stream. Credited to SDTRD's
  multi-agent worktree protocol.
- **Living specs:** with `[specs] living = true`, each spec names its `capability` in `status.yml`, and
  `check_living_specs` keeps `specs/living/<capability>.md` current: the criteria in force (tests-locked or
  implemented specs, which reach main only with their code) and coming (approved), superseded ones left out. `--write` regenerates them; the PR check fails when
  they are stale. Test ids don't change. Credited to SDTRD's living specs. See `docs/living-specs.md`.
- **Research and design step for large specs:** `research.md` (options, trade-offs, a decision) and `design.md`
  (interfaces, data flow, budgets, test seams) next to `spec.md`, reviewed in the spec PR. A spec takes the step with
  `design: yes` in `status.yml` (`new_spec.py --design` adds both files), or when it has at least `[specs]
  design_from_criteria` criteria (default 0: off). From `approved` on, `check_ac_traceability --spec-only` requires
  both files, a `Chosen: ...` decision and no open design questions. Credited to SDTRD's research and design gates.
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
