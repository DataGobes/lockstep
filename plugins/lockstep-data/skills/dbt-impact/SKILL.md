---
name: dbt-impact
description: Show what a dbt change affects before and after implementing it - changed models, everything downstream in dbt, enforced contracts that need a new model version, consumers outside dbt from Unity Catalog lineage (Genie spaces, dashboards, jobs), and a data-diff plan with dbt-audit-helper. Use when writing a spec for dbt work, before opening a dbt PR, or when someone asks what a model change breaks, who uses a table, or for a data diff.
---

# dbt impact

Find out who a dbt change touches, so the spec and the reviewer know before anything ships. Read only: never
change data, and never query tables that hold personal data.

Paths below are relative to this skill's folder. `scripts/impact.py` needs Python 3.11+ and nothing else.

## 1. Get the two manifests

- The branch: run `dbt parse` in the dbt project, which writes `target/manifest.json`.
- Prod: the `dbt-prod-state` artifact of the latest deploy pipeline run on main. Download it from that run in Azure
  DevOps, or with `az pipelines runs artifact download --artifact-name dbt-prod-state --path prod-state --run-id <id>`.
  Before the first prod deploy there is none: say so, and list the models in the change by hand.

## 2. Run the report

```
python3 scripts/impact.py --manifest <project>/target/manifest.json --state prod-state/manifest.json
```

It lists what changed (body, config or column types), what was removed, everything downstream in dbt including
exposures, and which changed models have an **enforced contract**.

## 3. Read it with the user

- **Enforced contracts:** a change to one needs a new model version (`versions:` in the model's YAML, with the old
  version kept and a deprecation date), described in the spec. Never edit the contracted version in place.
- **Removed models:** anything reading them breaks. Find those readers in step 4 before going on.
- **Downstream in dbt:** these rebuild in Slim CI. Check the ones whose logic depends on the changed columns.

## 4. Consumers outside dbt

The report ends with a SQL query on `system.access.table_lineage` for the changed tables. Ask the user to run it on a
SQL warehouse as themselves (or run it through an approved Databricks connector against the system catalog only), and
paste the result. It shows Genie spaces, dashboards, jobs and notebooks that read the tables. For column-level detail,
the same filter works on `system.access.column_lineage` with `source_column_name`.

## 5. Plan the data diff

For each changed model that exists in prod, the report gives a `dbt-audit-helper` `compare_all_columns` call: fill in
the primary key and run it against dev or CI (`dbt compile --inline` or an analysis). Expected differences go in the
spec's section 6 (risks, rollout, rollback); unexpected ones are bugs or a missing criterion.

## 6. Record it

Put the summary (changed, downstream, contracts, outside consumers, expected data diff) in the spec's section 4 when
writing a spec, or in the PR description for an implementation PR. Never paste query results that contain row-level
data, only table and object names and counts.
