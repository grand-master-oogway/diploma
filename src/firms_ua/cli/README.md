# cli

`firms-ua <command>` (a console script declared in `pyproject.toml`, installed with the package). `main.py` builds the parser and dispatches; each command module has `register(sub)` and `run(args, settings)`
returning the number of failures (exit code 1 if non-zero).

- `ingest.py`: `fetch`, `build-bronze`, `ingest`.
- `probe.py`: `probe`.
- `smoke.py`: `smoke`.
- `bigquery.py`: `bq-schemas`, writes the BigQuery external-table specs Terraform reads (`infra/modules/bigquery/schemas/`).
- `profile.py`: `profile-bronze [--start YYYY-MM-DD] [--end YYYY-MM-DD]`, read-only bronze statistics as JSON (see `ops/bronze_profile.py`).
