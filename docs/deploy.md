# Deploying and running the pipeline

## How code reaches the VM (CD)

```
push to main -> GitHub Actions: tests -> build image -> push to Artifact Registry -> VM pulls it when `firms-run` runs
```

- `.github/workflows/ci.yml` runs the tests on every pull request and push.
- `.github/workflows/deploy.yml` runs on every push to `main` that touches `src/`, `Dockerfile`, `pyproject.toml` or the workflow
  itself. It calls the tests first; only if they pass does it build the image and push it as `firms-ua:<commit sha>` and `firms-ua:latest`.
- GitHub authenticates to Google with Workload Identity Federation (no keys). Only runs of the `main` branch of this repository can act as
  the deploy service account `firms-ua-dev-deploy`, which may only push to the registry.
- The VM runs `firms-run`, which pulls `:latest` before each run. Nothing is installed by hand.

No manual build or deploy command exists. A change ships by merging to `main`.

## One-time setup

1. Create the cloud side (after reviewing the plan):

   ```
   cd infra\envs\dev
   terraform plan
   terraform apply
   terraform output github_variables
   ```

2. In GitHub: repository **Settings > Secrets and variables > Actions > Variables**, add each value printed by
   `terraform output github_variables`: `GCP_PROJECT_ID`, `WIF_PROVIDER`, `DEPLOY_SERVICE_ACCOUNT`, `WIF_SERVICE_ACCOUNT`,
   `IMAGE_REPOSITORY`, `TF_STATE_BUCKET`. These are identifiers, not secrets.
3. Merge to `main` (or run the `deploy` workflow by hand from the Actions tab) to publish the first image.

## Using the VM

The VM (`firms-ua-dev-dagster`) is a Debian machine with Docker and a `firms-run` helper installed by its startup script. It has no public
IP, so connect through IAP (`gcloud` is at `$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd` in PowerShell):

```
gcloud compute ssh firms-ua-dev-dagster --zone europe-west1-b --project nasa-firms --tunnel-through-iap --strict-host-key-checking=no
sudo firms-run smoke
sudo firms-run ingest --source VIIRS_NOAA20_SP --date 2025-07-15
```

`firms-run` logs in to the registry with the VM's service account, pulls the latest image, and runs the CLI with
`FIRMS_STORAGE_ROOT=gs://firms-ua-dev`, `FIRMS_GCP_PROJECT=nasa-firms` and the MAP_KEY read from Secret Manager. No key or credential file
lives on the VM. `smoke` checks the VM's own service account: raw write and read, bronze write only (`--check silver:w` or
`--check bronze:rw` must fail with 403, as designed).

If the startup script changes, the VM must be restarted once for it to run again:
`gcloud compute instances reset firms-ua-dev-dagster --zone europe-west1-b --project nasa-firms`.

## Later

Dagster and its metadata database will run as extra containers (Docker Compose) on this VM; the deploy job will then also tell the VM to pull
and restart them. See `dagster_notes.md`.
