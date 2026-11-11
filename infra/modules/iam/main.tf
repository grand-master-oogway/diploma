locals {
  # component -> description
  components = {
    ingestion = "FIRMS ingestion: fetch to raw, then raw to bronze"
    deploy    = "CI/CD: pushes container images from GitHub Actions"
    plan      = "CI: terraform plan (read-only) from GitHub Actions"
    apply     = "CI: terraform apply from GitHub Actions (main branch only)"
    silver    = "Bronze to silver transform"
    gold      = "Gold feature build"
    training  = "Model training (reads gold, writes MLflow artifacts)"
  }
}

resource "google_service_account" "component" {
  for_each = local.components

  project      = var.project_id
  account_id   = "${var.project_name}-${var.env}-${each.key}"
  display_name = each.value
}

# Least-privilege matrix. objectCreator = create only (no overwrite, no delete).
# Ingestion: create + read in raw (reads raw objects and its own ingestion log), create-only in bronze.
# It cannot delete or overwrite anything; writes also use an if-generation-match=0 precondition in code.
resource "google_storage_bucket_iam_member" "ingestion_raw_create" {
  bucket = var.buckets["raw"]
  role   = "roles/storage.objectCreator"
  member = google_service_account.component["ingestion"].member
}

resource "google_storage_bucket_iam_member" "ingestion_raw_read" {
  bucket = var.buckets["raw"]
  role   = "roles/storage.objectViewer"
  member = google_service_account.component["ingestion"].member
}

resource "google_storage_bucket_iam_member" "ingestion_bronze_create" {
  bucket = var.buckets["bronze"]
  role   = "roles/storage.objectCreator"
  member = google_service_account.component["ingestion"].member
}

# Silver transform: read bronze, full object control on silver (partitions are rewritten).
resource "google_storage_bucket_iam_member" "silver_read_bronze" {
  bucket = var.buckets["bronze"]
  role   = "roles/storage.objectViewer"
  member = google_service_account.component["silver"].member
}

resource "google_storage_bucket_iam_member" "silver_write_silver" {
  bucket = var.buckets["silver"]
  role   = "roles/storage.objectAdmin"
  member = google_service_account.component["silver"].member
}

# Gold build: read silver, create-only in gold (snapshots are immutable).
resource "google_storage_bucket_iam_member" "gold_read_silver" {
  bucket = var.buckets["silver"]
  role   = "roles/storage.objectViewer"
  member = google_service_account.component["gold"].member
}

resource "google_storage_bucket_iam_member" "gold_write_gold" {
  bucket = var.buckets["gold"]
  role   = "roles/storage.objectCreator"
  member = google_service_account.component["gold"].member
}

# Training: read gold, write MLflow artifacts.
resource "google_storage_bucket_iam_member" "training_read_gold" {
  bucket = var.buckets["gold"]
  role   = "roles/storage.objectViewer"
  member = google_service_account.component["training"].member
}

resource "google_storage_bucket_iam_member" "training_write_artifacts" {
  bucket = var.buckets["artifacts"]
  role   = "roles/storage.objectAdmin"
  member = google_service_account.component["training"].member
}

# Optional human analyst read access.
resource "google_storage_bucket_iam_member" "analyst_read" {
  for_each = {
    for pair in setproduct(var.analyst_members, keys(var.buckets)) :
    "${pair[0]}|${pair[1]}" => pair
  }

  bucket = var.buckets[each.value[1]]
  role   = "roles/storage.objectViewer"
  member = each.value[0]
}
