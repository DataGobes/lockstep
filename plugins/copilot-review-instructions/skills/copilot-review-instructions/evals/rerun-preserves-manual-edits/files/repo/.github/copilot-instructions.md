# sales-analytics: review rules for this repository

Project-wide rules for the Data Platform project also apply; these add what is specific to this repo.

## Architecture boundaries
- Python under `src/ingest/` only lands raw data; it must never read from or write to dbt schemas (`staging`, `finance`).

## Domain rules
- Revenue is always EUR excluding VAT; flag any column or calculation named `*_incl_vat` in `models/marts/finance/`.
- Never use `select *` in the final select of a mart model. (Added by Priya after the 2026-05 Power BI column-order incident.)

<!-- Maintained with the copilot-review-instructions skill. Manual edits are kept on re-run. Last run: 2026-06-02 -->
