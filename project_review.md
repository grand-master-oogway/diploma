# Project plan and status

Living document: update the status column and "Open decisions" at the end of every session.
Last updated: 2026-11-05.

## Goal
E2E pipeline: NASA FIRMS VIIRS detections over Ukraine -> Parquet medallion (bronze/silver/gold) in GCS -> DuckDB queries -> Dagster orchestration -> MLflow model comparison. IaC: Terraform. CI/CD: GitHub Actions.

## Decisions made
| Topic | Decision |
|---|---|
| Cloud | GCP |
| Query engine | DuckDB (the only compute engine; no Polars) |
| Orchestrator | Dagster |
| Compute | single Compute Engine VM, Docker Compose (Dagster + MLflow) |
| Python | 3.14, local venv at `venv/` |
| Data | VIIRS only (no MODIS/Landsat); bbox 22.1,44.4,40.2,52.4, clipped to Ukraine polygon in silver |
| Key | `MAP_KEY` / `FIRMS_MAP_KEY` in `.env` (gitignored); later Secret Manager |

## Open decisions
- NRT vs SP: which to ingest, and how SP replaces NRT (TODO in `firms_client.py`). Plan: NRT daily, SP reconciliation weekly, silver partition rebuilt from SP.
- Satellites: default NOAA-20 + NOAA-21 (S-NPP historical only, ends 2026-11-01).
- ML target: undecided (binary / count / FRP). Gold built target-agnostic first.
- Ukraine boundary file: none yet (Natural Earth is the fallback).
- GCP project ID, region (default `europe-west1`), GitHub repo `owner/name`.

## Status
| # | Phase | Status | Where |
|---|---|---|---|
| 1 | Foundation (pyproject, ruff, pytest, settings) | done | `pyproject.toml`, `src/firms_ua/settings.py` |
| 2 | Bronze (client, window planner, raw writer, CLI) | done, local only | `src/firms_ua/{firms_client,windows,bronze,cli}.py` |
| 3 | Silver (typed, clip, flags, dedupe, H3) | next | - |
| 4 | Gold (H3 x period grid, features, snapshots) | todo | - |
| 5 | DuckDB query layer over `gs://` | todo | - |
| 6 | Dagster (assets, checks, schedules) | todo | - |
| 7 | MLflow + training (baselines, LightGBM, backtest) | todo | - |
| 8 | Terraform GCP (buckets, IAM, secrets) | written, never applied | `infra/` |
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
src/firms_ua/     pure logic (settings, windows, firms_client, bronze, cli)
tests/            pytest, no network
infra/            modules/{storage,iam,secrets}, envs/dev; README has bootstrap steps
.github/workflows ci.yml, terraform.yml
data/             local lake mirror (gitignored)
PLAN.md           this file; CLAUDE.md = conventions for the assistant
```

## Run it
```
venv\Scripts\python -m pytest -q
venv\Scripts\python -m ruff check src tests && venv\Scripts\python -m ruff format --check src tests
venv\Scripts\python -m firms_ua.cli ingest --source VIIRS_NOAA20_NRT --date 2026-11-03 [--end ...] [--force]
```

## Rules to keep (details live in the project skills)
- Bronze is raw and immutable; silver rebuilds whole partitions; gold is immutable snapshots referenced by MLflow.
- Never log or commit the MAP_KEY (it is in the URL path; use `redact`).
- Never `terraform apply`/`destroy` without explicit user confirmation.
- Describe outputs as thermal-anomaly activity, never as strikes.
