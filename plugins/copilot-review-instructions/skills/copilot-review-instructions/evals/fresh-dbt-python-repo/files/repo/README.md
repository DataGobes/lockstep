# sales-analytics

Ingests Salesforce and ERP data (Python, `src/ingest`) into the lake and models it with dbt (`dbt/`).

- `dbt/models/staging/<source>/` – one model per source table, `stg_<source>__<entity>`.
- `dbt/models/intermediate/` – reusable joins, `int_<entity>_<verb>`.
- `dbt/models/marts/<domain>/` – `fct_` / `dim_` models consumed by Power BI.
- `src/ingest/` – API clients and loaders. Run with `python -m ingest`.
