# orchestration

Dagster definitions: FIRMS API -> raw -> bronze -> silver. They are thin wrappers: the logic lives in `ingestion/`, `silver/`,
`common/sources.py` and `planning.py` (pure, no Dagster imports).

## What is here

| File | Content |
|---|---|
| `partitions.py` | `ingest_partitions`: one UTC day (from 2022-02-24) x one satellite (`noaa20`, `noaa21`, `snpp`); `silver_partitions`: one UTC day |
| `planning.py` | partitions -> request windows; ranges of days the schedule still has to fetch |
| `resources.py` | `FirmsPipeline`: settings, storages, throttled fetcher; MAP_KEY read at run time, never in run config |
| `assets.py` | `firms_raw` (fetch), `firms_bronze` (build Parquet, automation-driven) and its blocking `days_complete` check |
| `silver_assets.py` | `firms_h3_activity` and `firms_silver` (blocking and warning asset checks); they impersonate `FIRMS_SILVER_SERVICE_ACCOUNT` when set |
| `schedules.py` | `firms_ingest_job` (raw only), `ingest_schedule` (daily 06:00 UTC, every unmaterialized raw partition) the `ingestion_automation` sensor (builds bronze after raw), `firms_silver_job` and the `silver_automation` sensor |
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

Nothing is launched by hand. `ingest_schedule` (on by default, daily 06:00 UTC) requests every raw partition not materialized yet: its
first tick is the whole history, later ticks the new day plus any day whose run failed. `firms_bronze` has an automation condition
(eager, for every partition, not only the latest day), and the `ingestion_automation` sensor (on by default, checks every minute)
builds bronze for each raw partition just materialized. A manual `firms_raw` materialization from the UI also works.

## Silver

- `firms_h3_activity` and `firms_silver` read bronze day D (all satellites, `MultiToSingleDimensionPartitionMapping`).
  `firms_silver` also reads the activity of D-365..D-1 (hotspot flag) and the last hour of bronze D-1 (pass ids).
- Automation (`silver_automation`, on by default): a day is rebuilt when anything it reads changes. Missing upstream
  partitions do not block, because (day, satellite) partitions a satellite does not cover are never materialized; a day
  built before all satellites arrived is rebuilt when they do.
- History is not built automatically. Backfill once from the UI: `firms_silver_job`, all partitions from 2022-02-24
  (single run; it processes 31 days at a time). Activity is built first in the same run, so hotspot flags are complete.
- A day that fails a blocking check is not written (its previous version stays) and the run fails, listing the days.
- On the VM the assets act as the `silver` service account (bronze read, silver write/delete); Terraform lets the VM's
  ingestion account impersonate it (`roles/iam.serviceAccountTokenCreator`).
