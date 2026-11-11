# orchestration

Dagster definitions for the ingestion: FIRMS API -> raw -> bronze. They are thin wrappers: the logic lives in `ingestion/`,
`common/sources.py` and `planning.py` (pure, no Dagster imports), and every step also runs from the CLI.

## What is here

| File | Content |
|---|---|
| `partitions.py` | `ingest_partitions`: one UTC day (from 2022-02-24) x one satellite (`noaa20`, `noaa21`, `snpp`) |
| `planning.py` | partitions -> request windows; partitions refreshed by the forward fill |
| `resources.py` | `FirmsPipeline`: settings, storages, throttled fetcher; MAP_KEY read at run time, never in run config |
| `assets.py` | `firms_raw` (fetch), `firms_bronze` (build Parquet) and its blocking `windows_complete` check |
| `schedules.py` | `firms_ingest_job` and `forward_fill_schedule` (daily 06:00 UTC, last 3 days; days already fetched are skipped) |
| `definitions.py` | the code location |

## How a run works

- A run gets a set of partitions. Both assets use a single-run backfill policy, so a backfill over the whole history is one run that
  receives all its partitions at once.
- `firms_raw` leaves out days the ingestion log already covers (in any window, from any run), then plans 5-day windows on a fixed grid
  for the rest (SP up to 2026-07-31, NRT after; days a satellite does not cover are skipped). So each day is fetched once and bronze
  gets no duplicates. It fails the run if any request failed, runs in the `firms_api` pool (limit 1), and waits for the MAP_KEY budget
  before each request. `force: true` in run config refetches (manual repair only).
- `firms_bronze` builds Parquet from the raw objects that hold the run's days. Its `days_complete` check passes only if every
  `(source, day)` is logged `ok` for both raw and bronze (a logged zero-row day counts as done).
- The ingestion log in the raw bucket is the record of what was fetched. Dagster's own metadata (SQLite in `DAGSTER_HOME`) only holds
  run history and partition status.
- Partitions a satellite does not cover (NOAA-21 before 2023-03-01, S-NPP after its last day) still materialize, with zero windows.

## Run locally

```
$env:DAGSTER_HOME = "$PWD\.dagster"      # any empty folder; ignored by git
$env:FIRMS_STORAGE_ROOT = "./data"
dagster dev -m firms_ua.orchestration.definitions
```

Backfill: in the UI open `firms_raw` -> Materialize -> select partitions. The forward-fill schedule starts stopped; turn it on in the UI.
