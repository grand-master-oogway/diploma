# Project plan and status

Living document: update the status column and "Open decisions" at the end of every session.
Last updated: 2026-11-05.

## Goal
E2E pipeline: NASA FIRMS VIIRS detections over Ukraine -> Parquet medallion (bronze/silver/gold) in GCS -> DuckDB queries -> Dagster orchestration -> MLflow model comparison. IaC: Terraform. CI/CD: GitHub Actions.

## Decisions made
| Topic | Decision |
|---|---|
| Cloud | GCP |
| Processing engine | Polars for all transforms (fetch -> bronze -> silver -> gold, writes Parquet) |
| Query engine | DuckDB, read-only over the Parquet in buckets (views, ad-hoc SQL); never writes the layers |
| Orchestrator | Dagster |
| Compute | single Compute Engine VM, Docker Compose (Dagster + MLflow) |
| Python | 3.14, local venv at `venv/` |
| Data | VIIRS only (no MODIS/Landsat); bbox 22.1,44.4,40.2,52.4, clipped to Ukraine polygon in silver |
| Key | `MAP_KEY` / `FIRMS_MAP_KEY` in `.env` (gitignored); later Secret Manager |

## Open decisions
- NRT vs SP: which to ingest, and how SP replaces NRT (TODO in `firms_client.py`). Plan: NRT daily, SP reconciliation weekly, silver partition rebuilt from SP.
- Satellites: default NOAA-20 + NOAA-21 (S-NPP historical only, ends 2026-11-01). NOAA-21 SP starts 2023-03-01.
- ML target: undecided (binary / count / FRP). Gold built target-agnostic first.
- Ukraine boundary file: none yet (Natural Earth is the fallback).
- GCP project ID, region (default `europe-west1`), GitHub repo `owner/name`.

## Status
| # | Phase | Status | Where |
|---|---|---|---|
| 1 | Foundation (pyproject, ruff, pytest, settings) | done | `pyproject.toml`, `src/firms_ua/common/settings.py` |
| 2a | Raw layer: unchanged API CSV bytes, one object per request (`raw/firms/source=/start_date=/day_range=/requested_at=.csv`), never overwritten; written by `fetch` | done, local only | `src/firms_ua/raw/` |
| 2b | Bronze: raw CSV -> all-string Parquet via Polars, Hive-partitioned by `source`/`acq_date` (a 5-day response becomes 5 daily files), versioned (`bronze/firms_viirs/v1/...`), nullable `type` (SP only), lineage columns `day_range`/`requested_at`/`start_date`; zero-row responses write no bronze file (to be recorded in the ingestion log); layout declared in `datacatalog` (pandera). API only fetches the Ukraine bbox, strict boundary clip happens in silver | done, local only | `src/firms_ua/{firms_api,bronze,raw,common}/`, `src/firms_ua/datacatalog_core/`, `src/firms_ua/datacatalog/`, `src/logger/` |
| 2c | Storage backend: `Storage` interface with `LocalStorage` (tmp file + hard link, never overwrites) and `GcsStorage` (`if_generation_match=0`, ADC); `FIRMS_STORAGE_ROOT` = `./data` or `gs://firms-ua-dev` (layer appended). Verified live against the dev buckets | done | `src/firms_ua/storage/` |
| 2d | Ingestion log: table `raw.ingestion_log` (one small file per entry: stage raw/bronze, status ok/failed, http status, rows, bytes, redacted error) in the raw bucket; `fetch`/`build-bronze` skip finished work from the log, log failures and continue, exit code 1 if any failed; zero-row responses are logged ok with rows=0 | done | `src/firms_ua/ingestion/`, `src/firms_ua/datacatalog/ingestion_log.py` |
| 2e | `probe` (availability, NRT retention, request cost, S-NPP gap; findings in `docs/probe_findings.md`) and `smoke` (key, FIRMS and bucket access of the current identity) commands; MAP_KEY can come from Secret Manager (`FIRMS_MAP_KEY_SECRET`) | done, run locally | `src/firms_ua/{ops,cli}/`, `src/firms_ua/common/secrets.py` |
| 2f | Deploy: `Dockerfile`, Artifact Registry (`firms-ua-dev`), VM startup script installs Docker + `firms-run` helper; applied 2026-11-10; `firms-run smoke` passes on the VM with the ingestion service account (silver/gold/artifacts writes and bronze reads are refused, as designed). **CD:** `deploy.yml` builds and pushes the image on every push to `main` via Workload Identity Federation (Terraform written and planned, not yet applied; Cloud Build removed) | in progress | `Dockerfile`, `infra/modules/{registry,github_oidc}`, `.github/workflows/deploy.yml`, `docs/deploy.md` |
| 3 | Silver (typed, clip, flags, dedupe, H3) | next | - |
| 4 | Gold (H3 x period grid, features, snapshots) | todo | - |
| 5 | DuckDB query layer over `gs://` | todo | - |
| 6 | Dagster (assets, checks, schedules) | todo | - |
| 7 | MLflow + training (baselines, LightGBM, backtest) | todo | - |
| 8 | Terraform GCP (project `nasa-firms`, europe-west1): raw/bronze/silver/gold/artifacts buckets with soft delete, per-component service accounts (ingestion = fetch + raw->bronze), Secret Manager container, VPC + Cloud NAT, Dagster VM. State bucket `gs://nasa-firms-tfstate` created. applied 2026-11-10: 32 resources created | applied | `infra/` |
| 9 | CI (ruff, pytest) | written, not yet run on GitHub | `.github/workflows/ci.yml` |
| 9b | Terraform CI (fmt/validate/tflint, plan) | written; `plan` skipped until WIF vars set | `.github/workflows/terraform.yml` |
| 9c | CD (build image, deploy to VM) | todo | - |
| 10 | Docs / thesis metrics | todo | - |

## Next steps (in order)
1. Silver layer locally (needs satellite choice + boundary file).
2. GCS storage backend for bronze/silver writers (currently local paths only).
3. Bootstrap GCP per `infra/README.md`, review `terraform plan`, apply only with explicit approval.
4. Set GitHub repo variables for WIF; first push to run CI.
5. Dagster local, then gold, then MLflow.

## Layout
```
src/firms_ua/
  common/     settings, secrets, errors, windows
  storage/    Storage interface, local, gcs, open_storage
  firms_api/  FIRMS client and models
  raw/        raw layer store
  bronze/     raw -> bronze builder
  ingestion/  ingestion log + runner (fetch_windows, build_objects)
  ops/        probe, smoke
  cli/        main + one module per command
  datacatalog_core/  ParquetTable base class   datacatalog/  table definitions
src/logger/   console-only logging config, top-level so every package can use it
tests/        mirrors the packages (tests/<package>/test_*.py); tests/fakes.py = in-memory GCS fake
infra/        modules/{storage,iam,secrets,network,vm,registry,github_oidc}, envs/dev; README has bootstrap steps
.github/workflows  ci.yml, terraform.yml, deploy.yml
docs/         dagster_notes, probe_findings, deploy
data/         local lake mirror (gitignored)
project_review.md this file (decisions, status, next steps)
```

## Run it
```
venv\Scripts\python -m pytest -q
venv\Scripts\python -m ruff check src tests && venv\Scripts\python -m ruff format --check src tests
venv\Scriptsirms-ua fetch|build-bronze|ingest --source VIIRS_NOAA20_NRT --date 2026-11-03 [--end ...] [--force]
```

## Rules to keep (details live in the project skills)
- Raw (original CSV bytes) and bronze (string Parquet) are immutable; silver rebuilds whole partitions; gold is immutable snapshots referenced by MLflow.
- Never log or commit the MAP_KEY (it is in the URL path; use `redact`).
- Never `terraform apply`/`destroy` without explicit user confirmation.
- Describe outputs as thermal-anomaly activity, never as strikes.
