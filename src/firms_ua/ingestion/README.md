# ingestion

Running the pipeline steps over many windows and remembering what happened.

- `log.py`: the ingestion log (`LogEntry`, `record`, `read_log`, `ok_windows`, `missing_windows`, `ok_requests`); table definition in
  `datacatalog/ingestion_log.py`.
- `runner.py`: `fetch_windows` and `build_objects` skip finished work, log every outcome, and keep going after a failure. The CLI and
  the Dagster assets call these.
- `throttle.py`: `TransactionBudget`, a sliding-window limit on MAP_KEY transactions (2 per requested day), so a backfill waits instead
  of hitting HTTP 429.
