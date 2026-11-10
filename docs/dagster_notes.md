# Dagster notes for the FIRMS pipeline

Nuances to settle before writing any Dagster code. Items marked **(verify)** must be checked against the docs of the
installed version first, because Dagster's API changes quickly (asset checks, concurrency pools, backfill policies).

Checked so far: `pip install --dry-run` resolves `dagster` 1.13.29 and `dagster-webserver` 1.13.29 on the project's
Python 3.14 venv. Nothing is installed or run yet.

## Setup

1. **Python and versions.** Stay on Python 3.14 (3.14.5 or newer), no 3.15-only syntax. Pin `dagster` and
   `dagster-webserver` to the same version.
2. **No `dagster-gcp`.** It pulls in BigQuery and pandas packages we do not need. Use `google-cloud-storage` directly in
   our own storage resource (the dependency is confirmed with the project owner before it is added).
3. **Thin wrappers.** All logic stays in `src/firms_ua/` as pure functions. Assets only map a partition to a function.
   Every step also runs from the CLI without Dagster.

## Design decisions to take before coding

4. **Partition unit vs request window (key decision).** Assets are naturally daily (UTC) partitions from 2022-02-24,
   but the backfill requests 5-day windows and the NRT job re-fetches the last 2-3 days.
   - Recommended: daily partitions plus a single-run backfill policy (`BackfillPolicy.single_run()` or `multi_run`,
     **verify**). The asset receives a date range and cuts aligned 5-day windows itself. One raw object then covers
     several partitions, so lineage lives in the ingestion log, not in partition identity.
   - Alternative: static partitions, one per 5-day window (324 per source for SP). Natural for the backfill, awkward for
     the NRT re-fetch.
5. **Source dimension.** Six sources times about 1,600 days. Either one asset per source built by a factory, or a
   two-dimensional partition (date x source, about 9,600 keys, heavy in the UI).
6. **Raw to bronze mapping.** One raw object feeds up to 5 `acq_date` bronze partitions, so the partition mapping between
   the raw asset and the bronze asset is many-to-many (**verify** available partition mappings).

## Data and storage

7. **No default pickle IO manager.** Assets write through our storage resource and return `MaterializeResult` metadata
   (rows, bytes, window, never a URL).
8. **Re-materialization is not overwrite.** Re-running a partition writes a new raw object (new `requested_at`) and new
   bronze files. GCS `if_generation_match=0` stops any object from being replaced. Duplicates are expected and are
   resolved in silver.

## Quality, retries, limits

9. **Blocking asset checks.** Quality gates are asset checks on the bronze asset with `blocking=True` (**verify**), so
   downstream assets do not run after a failure. "Window complete" and "row counts agree" read the ingestion log.
10. **Retries in one place.** `fetch` already retries network errors, 429 and 5xx with backoff. Do not add a Dagster
    `RetryPolicy` for the same errors, or retries multiply. Validation and schema failures are never retried.
11. **Concurrency.** Limit the ingestion asset with a concurrency pool of 2-3 (instance-level config in the open-source
    edition, **verify**) plus run-queue limits, so a backfill cannot exhaust 5,000 requests per 10 minutes per key.

## Secrets and logging

12. **Secrets leak surface.** Dagster stores run config, logs, event metadata and exception traces in its metadata
    database and shows them in the UI. The MAP_KEY must come from a resource that reads Secret Manager at run time through
    Application Default Credentials. It must never appear in run config, asset metadata, logged URLs or exception text.
    Keep the redaction used by the current client.
13. **Logging.** Do not call `configure_logging` inside assets. Use `context.log` or module loggers that Dagster
    captures (**verify** the `python_logs` settings) to avoid duplicate or leaked output.

## Schedules and operations

14. **Daemon.** Schedules and sensors need the `dagster-daemon` process, not just the webserver. Set
    `execution_timezone="UTC"` on every schedule.
15. **Jobs.**
    - NRT: re-fetch the last 2-3 days every ~3 hours (the real cadence comes from the probe).
    - S-NPP: stop after its end date, taken from configuration, not code.
    - SP catch-up: a monthly job reads the availability endpoint and backfills new SP windows.
16. **Deployment on the Dagster VM.** Docker Compose with webserver, daemon, code location and a Postgres metadata
    database. No public port (IAP tunnel to the UI). The attached service account provides Application Default
    Credentials, Cloud NAT provides egress. No ad-hoc analytics on this VM; that belongs on the separate analytics VM.

## Local development and tests

17. Use `dagster dev` with the local storage backend; the same code runs against `gs://` through configuration.
18. Test the pure functions with pytest. Add one test that the `Definitions` object loads and one `materialize` run with
    in-memory resources.
