# Design: <short title>

After the criteria, before the tests: how the chosen option fits into the system. One or two pages. Every
criterion in spec.md must be reachable from a seam in section 5.

## 1. Overview and invariants
What changes, in a paragraph, and what must stay true (for example: one row per customer, no personal data leaves
the gold layer, the model is deterministic for the same input).

## 2. Interfaces, data contracts and state
New or changed functions, tables, columns, APIs, prompts, with their types and versions.

## 3. Data flow
A diagram (Mermaid) or a numbered list: where data comes from, what transforms it, where it goes.

## 4. Boundaries and budgets
Which parts are pure logic and which do I/O; time, cost and resource budgets that match the non-functional criteria.

## 5. Test seams
Where each criterion is tested from: a public function, a dbt model's output, a prompt's response.

| AC | Seam | Test type |
|----|------|-----------|

## 6. Open questions
Must be empty before the spec's status becomes approved.
