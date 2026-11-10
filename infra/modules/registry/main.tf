resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "${var.project_name}-${var.env}"
  format        = "DOCKER"
  description   = "Container images of the FIRMS pipeline"
  labels        = var.labels
}

resource "google_artifact_registry_repository_iam_member" "reader" {
  for_each = toset(var.reader_members)

  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = each.value
}

resource "google_artifact_registry_repository_iam_member" "writer" {
  for_each = toset(var.writer_members)

  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.writer"
  member     = each.value
}
