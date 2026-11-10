locals {
  layers = ["raw", "bronze", "silver", "gold", "artifacts"]

  # Versioning on everything except silver (rebuilt from bronze, overwrite is normal).
  versioned = {
    raw       = true
    bronze    = true
    silver    = false
    gold      = true
    artifacts = true
  }
}

resource "google_storage_bucket" "layer" {
  for_each = toset(local.layers)

  name                        = "${var.project_name}-${var.env}-${each.key}"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy
  labels                      = var.labels

  versioning {
    enabled = local.versioned[each.key]
  }

  # Deleted or overwritten objects stay recoverable for this long.
  soft_delete_policy {
    retention_duration_seconds = var.soft_delete_retention_seconds
  }

  # Raw and bronze are rarely re-read, move them to a colder tier.
  dynamic "lifecycle_rule" {
    for_each = contains(["raw", "bronze"], each.key) ? [1] : []
    content {
      condition {
        age = var.bronze_coldline_after_days
      }
      action {
        type          = "SetStorageClass"
        storage_class = "COLDLINE"
      }
    }
  }

  # Drop old noncurrent versions on versioned buckets to bound cost.
  dynamic "lifecycle_rule" {
    for_each = local.versioned[each.key] ? [1] : []
    content {
      condition {
        days_since_noncurrent_time = var.noncurrent_expire_days
        with_state                 = "ARCHIVED"
      }
      action {
        type = "Delete"
      }
    }
  }

  # Artifacts: expire old noncurrent objects only; current model files stay.
}
