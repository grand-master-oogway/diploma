locals {
  env    = "dev"
  labels = { project = "firms-ua", env = local.env }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "storage.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "compute.googleapis.com",
    "iap.googleapis.com",
    "artifactregistry.googleapis.com",
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

module "registry" {
  source = "../../modules/registry"

  project_id     = var.project_id
  env            = local.env
  region         = var.region
  labels         = local.labels
  reader_members = [module.iam.service_account_members["ingestion"]]
  writer_members = [module.iam.service_account_members["deploy"]]

  depends_on = [google_project_service.apis]
}

# GitHub Actions authenticates without keys (Workload Identity Federation) and acts as the deploy / plan accounts.
module "github_oidc" {
  source = "../../modules/github_oidc"

  project_id                = var.project_id
  env                       = local.env
  github_repository         = var.github_repository
  deploy_service_account_id = module.iam.service_account_names["deploy"]
  plan_service_account_id   = module.iam.service_account_names["plan"]

  depends_on = [google_project_service.apis]
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
    registry_host  = module.registry.registry_host
    image          = "${module.registry.repository_url}/firms-ua:latest"
    storage_root   = "gs://${var.project_name}-${local.env}"
    project_id     = var.project_id
    map_key_secret = "projects/${var.project_id}/secrets/${module.secrets.map_key_secret_id}"
  }), "\r", "")

  depends_on = [module.registry]
}
