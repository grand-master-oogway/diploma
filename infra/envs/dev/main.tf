locals {
  env    = "dev"
  labels = { project = "firms-ua", env = local.env }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com", # service account impersonation (Dagster acts as the silver account)
    "bigquery.googleapis.com",
    "bigqueryconnection.googleapis.com", # BigLake connection reading the lake buckets
    "secretmanager.googleapis.com",
    "compute.googleapis.com",
    "iap.googleapis.com",
    "oslogin.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

module "storage" {
  source = "../../modules/storage"

  project_id    = var.project_id
  env           = local.env
  region        = var.region
  force_destroy = true # dev only
  labels        = local.labels

  depends_on = [google_project_service.apis]
}

module "iam" {
  source = "../../modules/iam"

  project_id      = var.project_id
  env             = local.env
  buckets         = module.storage.bucket_names
  analyst_members = var.analyst_members

  depends_on = [google_project_service.apis]
}

# Bronze and silver queryable from BigQuery as BigLake external tables (no data copied).
module "bigquery" {
  source = "../../modules/bigquery"

  project_id      = var.project_id
  project_name    = var.project_name
  env             = local.env
  region          = var.region
  buckets         = module.storage.bucket_names
  analyst_members = var.analyst_members
  labels          = local.labels

  depends_on = [google_project_service.apis, google_project_iam_member.apply]
}

module "secrets" {
  source = "../../modules/secrets"

  project_id       = var.project_id
  env              = local.env
  labels           = local.labels
  accessor_members = [module.iam.service_account_members["ingestion"]]

  depends_on = [google_project_service.apis]
}

module "network" {
  source = "../../modules/network"

  project_id = var.project_id
  env        = local.env
  region     = var.region

  depends_on = [google_project_service.apis]
}

# GitHub Actions authenticates without keys (Workload Identity Federation) and acts as the deploy / plan accounts.
module "github_oidc" {
  source = "../../modules/github_oidc"

  project_id                = var.project_id
  env                       = local.env
  github_repository         = var.github_repository
  github_repository_id      = var.github_repository_id
  deploy_service_account_id = module.iam.service_account_names["deploy"]
  plan_service_account_id   = module.iam.service_account_names["plan"]
  apply_service_account_id  = module.iam.service_account_names["apply"]

  depends_on = [google_project_service.apis]
}

# The apply account manages exactly the resource types in this configuration. projectIamAdmin and serviceAccountAdmin let
# it change IAM, which makes it effectively an administrator of the project: only main-branch runs of this repository
# can use it (see github_oidc and .github/workflows/terraform.yml).
resource "google_project_iam_member" "apply" {
  for_each = toset([
    "roles/storage.admin",                   # buckets and bucket IAM
    "roles/compute.admin",                   # network, firewall, router/NAT, VM and its IAM
    "roles/iam.serviceAccountAdmin",         # service accounts and their IAM
    "roles/iam.serviceAccountUser",          # attach the ingestion account to the VM
    "roles/iam.workloadIdentityPoolAdmin",   # GitHub OIDC pool and provider
    "roles/resourcemanager.projectIamAdmin", # project-level role bindings
    "roles/secretmanager.admin",             # MAP_KEY secret container and its IAM (not the secret value)
    "roles/iap.admin",                       # IAP tunnel permission on the VM
    "roles/serviceusage.serviceUsageAdmin",  # enable APIs
    "roles/bigquery.admin",                  # datasets, external tables, the BigLake connection and their IAM
  ])

  project = var.project_id
  role    = each.key
  member  = module.iam.service_account_members["apply"]
}

resource "google_storage_bucket_iam_member" "apply_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = module.iam.service_account_members["apply"]
}

# The plan account reads every resource and the IAM policies, and may use the Terraform state bucket (read state, hold the lock).
resource "google_project_iam_member" "plan" {
  for_each = toset(["roles/viewer", "roles/iam.securityReviewer"])

  project = var.project_id
  role    = each.key
  member  = module.iam.service_account_members["plan"]
}

resource "google_storage_bucket_iam_member" "plan_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = module.iam.service_account_members["plan"]
}

module "vm" {
  source = "../../modules/vm"

  project_id            = var.project_id
  env                   = local.env
  zone                  = "${var.region}-b"
  subnetwork_self_link  = module.network.subnetwork_self_link
  service_account_email = module.iam.service_account_emails["ingestion"]
  labels                = local.labels

  # Strip any CR so the bash script is valid even if a Windows checkout turned the template into CRLF.
  startup_script = replace(templatefile("${path.module}/startup.sh.tftpl", {
    storage_root           = "gs://${var.project_name}-${local.env}"
    project_id             = var.project_id
    map_key_secret         = "projects/${var.project_id}/secrets/${module.secrets.map_key_secret_id}"
    silver_service_account = module.iam.service_account_emails["silver"]
  }), "\r", "")

}

# Lets GitHub Actions copy the built package to the VM and install it, over an IAP tunnel and OS Login (no key, no public IP).
module "deploy_access" {
  source = "../../modules/deploy_access"

  project_id                     = var.project_id
  zone                           = module.vm.zone
  instance_name                  = module.vm.instance_name
  deploy_member                  = module.iam.service_account_members["deploy"]
  vm_service_account_resource_id = module.iam.service_account_names["ingestion"]

  depends_on = [google_project_service.apis]
}
