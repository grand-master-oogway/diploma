# Deploying and running the pipeline

## How code reaches the VM (CD)

```
push to main -> GitHub Actions: tests -> build a wheel -> copy it and deploy/vm/setup.sh to the VM over IAP
             -> install into /opt/firms-ua/venv, configure and restart Dagster
```

- `.github/workflows/ci.yml` runs the tests on every pull request and push.
- `.github/workflows/deploy.yml` runs on every push to `main` that touches `src/`, `deploy/`, `pyproject.toml` or the workflow itself (or
  by hand from the Actions tab). It runs the tests first; only if they pass does it build the package, copy it and `deploy/vm/setup.sh`
  to the VM (`gcloud compute scp`) and run `sudo setup.sh`, which installs the package and (re)configures Dagster.
- `.github/workflows/terraform.yml` plans infrastructure changes on pull requests and applies them automatically after the merge
  (see `infra/README.md`). Review the plan on the pull request: there is no later approval.
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

## Dagster

Two systemd services run on the VM as the `firms-ua` system user: `dagster-webserver` (UI on `127.0.0.1:3000` only) and `dagster-daemon`
(schedules, run queue, backfills). `DAGSTER_HOME` is `/var/lib/firms-ua/dagster`. It holds `dagster.yaml` and the SQLite metadata: run
history, event logs, partition status and schedule state. Pipeline data is never stored there. All of this is written by
`deploy/vm/setup.sh` on every deploy, so a change ships by merging, with no Terraform apply or VM reset. The deploy restarts both
services, which interrupts runs in progress. Re-launch them: days already fetched are skipped.

Open the UI through an IAP tunnel, then browse to http://localhost:3000:

```
gcloud compute ssh firms-ua-dev-dagster --zone europe-west1-b --project nasa-firms --tunnel-through-iap -- -N -L 3000:127.0.0.1:3000
```

Historical backfill: open `firms_raw` in the UI, then **Materialize**, select all partitions, and launch the backfill with the
downstream asset `firms_bronze`. The single-run policy makes this one run. The `firms_api` pool and the client-side budget (4,500 of 5,000
transactions per 10 minutes) pace the requests, so the full history takes about 30 minutes or more. Launching it again is safe.

Forward fill: turn on `forward_fill_schedule`. It runs daily at 06:00 UTC and looks at the last 3 complete days. Each day is fetched
only once: days already in the ingestion log are skipped, so normally only yesterday is requested and bronze gets no duplicates. NRT
detections that arrive after the fetch are not chased. SP replaces NRT later. `force: true` in the run config refetches a day; it is
for manual repair only, because it adds a second copy to bronze.

Logs: `journalctl -u dagster-daemon -f` and `journalctl -u dagster-webserver -f`.
