# A/B-testing the instructions with real Copilot reviews

Goal: see which rules Copilot follows, ignores or misreads, on an identical diff, with and without the new instructions.
Then refine the rules from that evidence.

## Pick the test change

Use a change that **should** trigger several of the new rules:
- Best: replay a real past PR where human reviewers left corrections that the new rules encode.
  Cherry-pick or re-apply its commits onto a fresh branch.
- Otherwise: write a small diff that deliberately violates 4–6 rules (one per area), plus one or two clean changes
  that should get **no** comment. Those check for noise.
- Azure DevOps limits: no more than 100 files and 100 changes, no merge conflicts.

Write down the expected comments **before** requesting reviews: rule → file:line it should flag.

## Azure DevOps (instructions are read from the target branch)

```bash
# from an up-to-date default branch, e.g. main
git switch main && git pull
git switch -c review-test/baseline               # target A: current rules only
git push -u origin review-test/baseline

git switch -c review-test/with-instructions      # target B: current rules + new instructions
git merge --no-ff chore/copilot-review-instructions -m "test: apply new review instructions"
git push -u origin review-test/with-instructions

git switch main && git switch -c review-test/change-a   # the test change, branched from main
#   ...apply the test change, commit...
git push -u origin review-test/change-a
git switch -c review-test/change-b                       # same commits, second source branch
git push -u origin review-test/change-b
```

Open two PRs (two source branches, because Azure DevOps allows only one active PR per source/target pair):
- PR A: `review-test/change-a` → `review-test/baseline`
- PR B: `review-test/change-b` → `review-test/with-instructions`

With `az`:
```bash
az repos pr create --source-branch review-test/change-a --target-branch review-test/baseline --title "[review-test] baseline"
az repos pr create --source-branch review-test/change-b --target-branch review-test/with-instructions --title "[review-test] with instructions"
```

Both change branches start from `main` and carry the same commits, so both PR diffs (computed against the merge base)
are identical. The instruction files exist only in target B, so they don't appear in PR B's diff.

Request **GitHub Copilot** as reviewer on both, with the same review effort. Each review costs AI credits.
Optionally run each twice to see how much results vary between runs. Re-requesting needs a new merge commit:
push a trivial follow-up commit, or retarget the PR.

Clean up afterwards: abandon both PRs and delete the four `review-test/*` branches.

## GitHub (instructions are read from the head branch)

The instruction PR is reviewed with its own new rules, but a PR that only adds instruction files has no code to review.
Do the same two-PR setup with the change on both branches: PR A without the instruction commits, PR B with them,
both targeting `main`.

## Scorecard

Fill one row per expected comment, plus one row per unexpected comment:

| # | Rule (file › heading) | Expected at | Baseline A | With rules B | Verdict |
|---|---|---|---|---|---|
| 1 | dbt › Boundaries: staging-only `source()` | models/intermediate/x.sql:7 | missed | flagged, cites rule | **followed** |
| 2 | python › settings via loader | src/jobs/load.py:12 | flagged (generic) | flagged, specific fix | improved |
| 3 | dbt › PK tests in models yml | models/marts/_x.yml | missed | missed | **ignored** |
| 4 | — (noise) | src/util.py:40 | — | style nit already enforced by ruff | **noise** |

Verdicts: **followed** (B flags it, A doesn't) · **improved** (both flag it, B is more specific or correct) ·
**ignored** (B misses it) · **misread** (B flags the wrong thing, citing the rule) · **noise** (an unwanted comment in B).

## Refine from the scorecard

- **Ignored:** make the rule more concrete. Name the exact path/function and what to flag, add a 2-line bad/good
  snippet, or move it higher in its file. Check that `applyTo` actually matches the changed file.
- **Misread:** the wording is ambiguous. Add the counter-example the model tripped on, or narrow the scope.
- **Noise:** usually a rule that is too broad, or Copilot duplicating a linter. Narrow the rule, or add a line that
  says what is out of scope ("Don't comment on formatting; sqlfluff enforces it in CI").
- **Followed everywhere:** keep it. Don't reword rules that work.
- Change only a few rules per iteration so you can tell which edit made the difference, and re-run the same test change.
- Feed general lessons (not repo-specific ones) back into the skill's `rule-quality.md`.
