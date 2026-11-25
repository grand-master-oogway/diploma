# Infrastructure (Terraform, GCP)

```
modules/storage   raw/bronze/silver/gold/artifacts buckets (uniform access, public access blocked)
modules/iam       one service account per component, least-privilege bucket roles; the ingestion account (Dagster VM) may impersonate the silver account
modules/bigquery  BigLake external tables over bronze and silver (datasets dev_bronze, dev_silver; no data copied)
modules/secrets   Secret Manager container for the FIRMS MAP_KEY (value added manually)
modules/network   VPC, subnet, Cloud Router + Cloud NAT, IAP-only firewall
modules/deploy_access  lets the GitHub deploy account reach the VM over IAP (OS Login with sudo)
modules/github_oidc  Workload Identity Federation so GitHub Actions can deploy without keys
modules/vm        Dagster VM (no external IP, runs as the ingestion service account)
envs/dev          dev environment (separate state); prod to be added the same way
```

Changes are applied by CI: a pull request shows `terraform plan` (read-only account); after the merge to `main`, the `apply` job
plans again and applies automatically, with no approval step. **Review the plan on the pull request before merging: it is the only
check.** The job uses the `apply` service account, which only main-branch runs can impersonate. Local `apply` is only for the bootstrap
below.

## Enabling CI apply (once)
1. Apply locally once, so the apply account and its bindings exist: `terraform plan` / `terraform apply` in `envs/dev`.
2. Add repository variable `APPLY_SERVICE_ACCOUNT` from `terraform output github_variables`.
3. Optional: in the GitHub environment `dev-infra` (Settings > Environments), limit deployment branches to `main`. Adding required
   reviewers turns on an approval step before every apply, if the GitHub plan offers it.

Until `APPLY_SERVICE_ACCOUNT` is set, the `apply` job is skipped.

## One-time bootstrap (manual)
1. `gcloud auth login && gcloud auth application-default login`
2. Create a state bucket (versioned): `gcloud storage buckets create gs://<state-bucket> --location=europe-west1 --uniform-bucket-level-access && gcloud storage buckets update gs://<state-bucket> --versioning`
3. `cd envs/dev && terraform init -backend-config="bucket=<state-bucket>"`
4. `terraform plan -var project_id=<project>` then, after review, `terraform apply`.
5. Add the key: `printf '%s' "$MAP_KEY" | gcloud secrets versions add firms-ua-dev-map-key --data-file=-`

## GitHub Actions to GCP (Workload Identity Federation, no JSON keys)
Create a pool/provider bound to this repo and a service account for CI with plan-level roles
(`roles/viewer` plus read on the state bucket). Then set repository **variables**:
`WIF_PROVIDER`, `WIF_SERVICE_ACCOUNT`, `TF_STATE_BUCKET`, `GCP_PROJECT_ID`.
Until `WIF_PROVIDER` is set, the `plan` job is skipped; `validate` (fmt, validate, tflint) always runs.
