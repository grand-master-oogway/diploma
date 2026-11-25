# docs

Project notes that do not belong in code.

- `dagster_notes.md`: nuances and open design decisions for the Dagster orchestration, to settle before writing assets.
- `probe_findings.md`: what FIRMS actually serves (availability, NRT retention, request cost, the S-NPP gap), measured on 2026-11-10.
- `deploy.md`: how code reaches the VM (GitHub Actions over IAP), what is installed there, and how to run commands on it.
- `bigquery.md`: querying bronze and silver from BigQuery (tables, example queries, cost, caveats).
- `silver_findings.json`: `firms-ua profile-bronze` over bronze 2022-02-24 .. 2026-11-24 (versions per source, UTC overpass hours,
  value quantiles, H3 r9 cells by active days per year); sets silver's label table, value ranges and hotspot threshold.
