# Rule-quality checklist

Run every proposed rule through this list before showing it to the user. `scripts/lint_instructions.py` catches
the mechanical failures; the judgment calls are yours.

## Contents
1. The checklist
2. Where rules come from (and where they must not come from)
3. Vague → checkable rewrites
4. When and how to add a bad/good snippet
5. Budget and ordering
6. Red flags

## 1. The checklist

A rule passes only if **all** are true:

1. **Checkable in a diff.** A reviewer looking only at changed lines (plus nearby context) can say "violated" or "not violated".
   Test: could you write the review comment it would produce? If not, rewrite or drop it.
2. **Specific to this repo.** It names this repo's real paths, layers, functions, macros, prefixes or types.
   A rule that would fit any repo belongs at project level, not here.
3. **Not already covered.** Not in the project/org instructions (even reworded), not enforced by a linter or CI step
   (ruff, sqlfluff, mypy, dbt tests, pre-commit), not already in an existing instruction file.
   Duplicates waste the budget, and lint-enforced rules make Copilot repeat what CI already says.
4. **Grounded.** It cites its source: a user answer, or files you actually read (`path:line`). An inferred rule needs
   at least two places in the code that follow it. One file is an accident, not a convention.
5. **Short and imperative.** One bullet, one requirement, ideally under ~200 characters. Start with a verb:
   "Use", "Select from", "Raise", "Never", "Keep".
6. **Scoped correctly.** Language- or folder-specific rules go in a path-scoped file whose `applyTo` matches only those files.
   The repo-wide file gets only rules that cross areas: architecture boundaries, domain rules, error-handling contracts,
   naming that spans languages.
7. **Supported.** Nothing about comment formatting, emoji, the PR overview, blocking or approving merges, or following links.
8. **No conflict with project rules,** unless the user explicitly chose to override one (see SKILL.md step 5).

## 2. Where rules come from

Rank sources by evidence strength:

1. **User answers** about what reviewers keep correcting. These outrank everything inferred. If code samples
   contradict an answer, ask; the code may be the legacy the user wants to move away from.
2. **Violations and fixes visible in the repo:** TODOs like "reviewers keep flagging this", commented-out
   anti-patterns, one file that breaks a pattern every sibling follows.
3. **Consistent patterns across sampled files:** layer boundaries (`staging` reads only `source()`), wrappers
   everything goes through (an HTTP client wrapper, a settings loader), error types, naming prefixes.
4. **Docs in the repo:** README, CONTRIBUTING, ADRs. Treat them as claims to verify against code, because docs drift.

Do not turn these into rules:
- Style that a formatter or linter in the repo already enforces. Check `pyproject.toml`, `.sqlfluff`,
  `.pre-commit-config.yaml` and the CI pipeline.
- Generic advice that holds everywhere ("write tests", "handle errors").
- Things only visible outside the diff ("make sure the dashboard still works").

## 3. Vague → checkable rewrites

| Vague | Checkable rule for a dbt + Python repo |
|---|---|
| Follow SOLID / separation of concerns | `Models in models/marts/ select only from ref('int_…') or ref('stg_…'); never from source().` |
| Use best practices for configuration | `Read configuration only through pipelines.settings.load(); flag any os.environ / os.getenv outside src/pipelines/settings.py.` |
| Handle errors properly | `Jobs raise a subclass of PipelineError (src/pipelines/errors.py); flag bare raise Exception(...) and except Exception: pass.` |
| Use consistent naming | `Name staging models stg_<source>__<entity> (double underscore), one model per source table.` |
| Keep models maintainable | `Put every new model in the _<folder>__models.yml file next to it, with unique and not_null tests on its primary key.` |
| Be careful with time zones | `Convert *_ts columns with {{ to_utc('col', 'source_tz') }} in staging; flag from_utc_timestamp or inline tz arithmetic elsewhere.` |
| Make HTTP calls robust | `Make outbound HTTP calls only via pipelines.http.RetryingSession; flag direct requests.get/post or httpx calls elsewhere.` |

The pattern: name the **place** (path or layer), the **required thing** (function, macro, type, prefix), and what to **flag**.

## 4. When and how to add a bad/good snippet

Add a snippet only when the rule is easy to misread: boundary rules, "use X instead of Y" rules where X and Y look
alike, or naming with subtle parts such as a double underscore. Skip it for rules that are clear in words.

- Use real code from this repo, shortened to 2–6 lines per side. Copilot matches patterns, and real ones match real diffs.
- Label the sides `# Avoid` / `# Prefer` (or `-- Avoid` / `-- Prefer` in SQL) inside one fenced block.
- Budget: at most ~1 snippet per 4 rules. Snippets cost more than bullets.

````markdown
- Read sources only in `models/staging/`. Other layers use `ref()` to a staging model.

```sql
-- Avoid (in models/intermediate/)
select id as product_id from {{ source('pim', 'product') }}
-- Prefer
select product_id from {{ ref('stg_pim__products') }}
```
````

## 5. Budget and ordering

- **10–20 rules in total** across all files on the first run. Fewer, sharper rules get followed more reliably than many.
- Spread them by where reviews hurt, not evenly by language.
- In each file put the highest-value rules first: boundaries and correctness, then domain rules, then naming.
- Use a few clear `##` headings per file (e.g. *Architecture boundaries*, *Error handling*, *Naming*). No headings with
  one bullet under them, unless that bullet is important.
- On re-runs, adding rules is fine when there is evidence (a missed issue, a new pain point). Prefer replacing a
  weak rule over growing past ~30.

## 6. Red flags

Rewrite or drop a rule if it:
- contains "appropriate", "properly", "best practice", "clean", "readable", "maintainable", "consistent" without saying what that means here;
- needs context outside the diff and the files it touches;
- restates a project-level rule in other words;
- describes how Copilot should write its comments;
- declares that this file overrides the project-wide instructions in general ("where they disagree, this file wins").
  On Azure DevOps repo rules already win, so a blanket line like that silently overrules every project rule. Override
  one rule at a time, scoped to the paths it concerns, and list each override in the PR description;
- can't name a single file in this repo where it applies.
