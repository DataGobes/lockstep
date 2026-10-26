---
id: 0042
title: <short title>
owner: <engineer>
reviewer: <engineer>
---

# <short title>

## 1. Problem and outcome
Who needs what, why, and how we will know it worked.

## 2. Scope / non-goals
- In scope: …
- Out of scope (agent must not touch): …

## 3. Acceptance criteria (EARS style, each testable)
- AC-001 WHEN <condition> THE SYSTEM SHALL <behaviour>.
- AC-002 (non-functional) THE pipeline SHALL complete in < 15 min on staging.

Never delete or renumber a criterion. To replace one, strike it and point to its replacement, here or in a later spec:
`- ~~AC-003~~ superseded by AC-004` or `- ~~AC-003~~ superseded by 0057/AC-001`.

## 4. Interfaces and data contract
Inputs, outputs, contract enforced?, versioning impact, downstream consumers (paste UC lineage query result).

## 5. Test and eval plan
Tests name criteria with this spec's id: `@pytest.mark.ac("0042/AC-001")`, dbt unit test `ac_0042_001_<what>`,
`meta: {ac: 0042/AC-001}`, or an `ac` field `0042/AC-001` in an eval row.

| AC | Test type | Location |
|----|-----------|----------|

## 6. Risks, rollout, rollback
Expected data-diff changes, feature flag, rollback plan.

## 7. Open questions
Must be empty before status becomes approved.
