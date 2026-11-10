# Deploying and running the pipeline

## How code reaches the VM (CD)

```
push to main -> GitHub Actions: tests -> build a wheel -> copy it to the VM over IAP -> install it into /opt/firms-ua/venv
```

- `.github/workflows/ci.yml` runs the tests on every pull request and push.
- `.github/workflows/deploy.yml` runs on every push to `main` that touches `src/`, `pyproject.toml` or the workflow itself (or by hand from
  the Actions tab). It runs the tests first; only if they pass does it build the package, copy it to the VM (`gcloud compute scp`) and
  install it (`sudo firms-ua-install`).
- GitHub authenticates to Google with Workload Identity Federation (no keys). Only runs of the `main` branch of this repository can act as
  the deploy service account `firms-ua-dev-deploy`. That account may log in to this one VM through the IAP tunnel (OS Login with sudo) and
  nothing else.
- The VM has no public IP and holds no GitHub credentials.

No manual deploy command exists. A change ships by merging to `main`.

## What is on the VM

The code is installed as a Python package into `/opt/firms-ua/venv` (Python 3.14, managed by `uv`). The VM's startup script prepares
everything else at boot: `uv`, the environment, the install helper `/usr/local/sbin/firms-ua-install`, and the `firms-ua` command, which
sets the storage root, the project and the Secret Manager key, then runs the CLI. The MAP_KEY is read from Secret Manager with the VM's own
service account; no key or credential file lives on the disk. Data is never stored on the VM: it goes to the Cloud Storage buckets.

## One-time setup

1. Create the cloud side (after reviewing the plan):

   ```
   cd infra\envs\dev
   terraform plan
   terraform apply
   terraform output github_variables
   ```

2. In GitHub: repository **Settings > Secrets and variables > Actions > Variables**, add each value printed by
   `terraform output github_variables`: `GCP_PROJECT_ID`, `WIF_PROVIDER`, `DEPLOY_SERVICE_ACCOUNT`, `WIF_SERVICE_ACCOUNT`, `TF_STATE_BUCKET`.
   These are identifiers, not secrets. (`IMAGE_REPOSITORY` from the earlier Docker setup is no longer used.)
3. Restart the VM once so the startup script runs: `gcloud compute instances reset firms-ua-dev-dagster --zone europe-west1-b --project nasa-firms`.
4. Merge to `main` (or run the `deploy` workflow by hand) to install the first version.

## Using the VM

Connect through IAP (`gcloud` is at `$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdkin\gcloud.cmd` in PowerShell):

```
gcloud compute ssh firms-ua-dev-dagster --zone europe-west1-b --project nasa-firms --tunnel-through-iap --strict-host-key-checking=no
firms-ua smoke
firms-ua ingest --source VIIRS_NOAA20_SP --date 2025-07-15
```

`smoke` checks the VM's own service account: raw write and read, bronze write only (`--check silver:w` or `--check bronze:rw` must fail with
403, as designed).

If the startup script changes in Terraform, restart the VM once for it to run again (step 3 above).

## Later

Dagster and its metadata database will run as systemd services on this VM; the deploy job will then also restart them. See `dagster_notes.md`.
