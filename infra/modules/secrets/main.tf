# Creates the secret container only. The value is added out of band:
#   printf '%s' "$KEY" | gcloud secrets versions add firms-ua-<env>-map-key --data-file=-
resource "google_secret_manager_secret" "map_key" {
  project   = var.project_id
  secret_id = "${var.project_name}-${var.env}-map-key"
  labels    = var.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = toset(var.accessor_members)

  project   = var.project_id
  secret_id = google_secret_manager_secret.map_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}
