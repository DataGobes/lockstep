<!--
Title: start with the Jira key, e.g. "MXAAI-123 Add churn features".
Prefixes the checks read: [test-change] for a deliberate change to locked tests, [large-approved] for a PR over 800 lines.
-->

**Spec:** specs/<id>-<slug>/spec.md
**PR type:** spec | tests | implementation | test-change
**Agent used:** Copilot | Claude | none

## What and why

<One or two sentences.>

## AC → test → result

| AC | Test | Result |
|----|------|--------|
| 0042/AC-001 | tests/test_x.py::test_y | passes |

## Assumptions

- <Anything you or the agent decided that the spec does not say.>

## Checklist

- [ ] PII routing respected: a spec with `pii: yes` was worked on with Copilot only.
- [ ] No existing test, fixture, snapshot or eval threshold changed (or the title starts with `[test-change]`).
- [ ] Fixtures use invented values only, such as "Test Person 001".

## Reviewer checklist

- [ ] Intent and scope match the spec; nothing outside it changed.
- [ ] Test changes: none, or justified by a criterion.
- [ ] No silent behaviour change for existing callers or downstream models.
- [ ] Unfamiliar APIs and functions exist in the pinned versions.
- [ ] New dependencies are needed and approved.
- [ ] No duplicated logic.
- [ ] No error masking (broad except, coalesce or try_cast hiding bad input).
- [ ] Security and PII: no secrets, no personal data in logs or fixtures.
- [ ] Contracts and lineage: enforced contracts get a new version; downstream consumers checked.
- [ ] Readable without the author explaining it.
