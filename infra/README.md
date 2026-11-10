# Infrastructure (Terraform, GCP)

```
modules/storage   raw/bronze/silver/gold/artifacts buckets (uniform access, public access blocked)
modules/iam       one service account per component, least-privilege bucket roles
modules/secrets   Secret Manager container for the FIRMS MAP_KEY (value added manually)
modules/network   VPC, subnet, Cloud Router + Cloud NAT, IAP-only firewall
modules/registry  Artifact Registry Docker repository (VM pulls, the GitHub deploy account pushes)
modules/github_oidc  Workload Identity Federation so GitHub Actions can deploy without keys
modules/vm        Dagster VM (no external IP, runs as the ingestion service account)
envs/dev          dev environment (separate state); prod to be added the same way
```

Never run `terraform apply` from CI. Apply locally after reviewing the plan.

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
