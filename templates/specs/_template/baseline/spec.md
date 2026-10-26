---
id: 0042
title: <area> as it works today
owner: <engineer>
reviewer: <engineer>
---

# <area> as it works today

A baseline spec describes behaviour the code already has, and pins it with tests that pass today. It changes no
code. Later change specs supersede its criteria like any other spec's. See docs/baseline-specs.md.

## 1. Problem and outcome
Which part of the system this pins, why now (it is about to change, it breaks often, nobody knows what it does), and
who relies on it.

## 2. Scope / non-goals
- In scope: the modules, models or endpoints this covers, by path.
- Out of scope: … (behaviour nearby that this baseline does not pin)
- Not a goal: changing anything. A behaviour that looks wrong is a bug report or an open question, not a criterion.

## 3. Acceptance criteria (each testable)
Each criterion states what the code does today, with where you saw it. Same formats as any spec: one EARS sentence,
or a title with Given/When/Then steps.

- AC-001 WHEN <input or event> THE SYSTEM SHALL <what it does today>.
  - Observed in: `<path>:<line>`
- AC-002 <short title>
  - GIVEN <starting state, with concrete values>
  - WHEN <the one action or event>
  - THEN <the observable outcome today>
  - Observed in: `<path>:<line>`

Never delete or renumber a criterion. When a change spec alters this behaviour, it strikes the criterion here and
points to its replacement: `- ~~AC-002~~ superseded by 0057/AC-001`.

## 4. Interfaces and data contract
The inputs and outputs these criteria are tested through, contracts already enforced, and known consumers.

## 5. Test and eval plan
Characterisation tests: they pass on today's code. Name criteria with this spec's id, as in any spec:
`@pytest.mark.ac("0042/AC-001")`, dbt unit test `ac_0042_001_<what>`, `meta: {ac: 0042/AC-001}`, or an `ac` field
`0042/AC-001` in an eval row. An existing test can be adopted by adding only the tag.

| AC | Test (new or adopted) | Location |
|----|-----------------------|----------|

## 6. Risks, rollout, rollback
Behaviour that depends on data, time or an external service, and how the tests pin it (fixtures, a frozen clock).

## 7. Open questions
Behaviour you could not tell intended from accidental. Must be empty before status becomes approved: each one
becomes a criterion, a non-goal or a bug report.
