locals {
  env    = "dev"
  labels = { project = "firms-ua", env = local.env }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "storage.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
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
  accessor_members =[module.iam.service_account_members["ingestion"]]

  depends_on = [google_project_service.apis]
}
