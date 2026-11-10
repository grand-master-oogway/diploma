output "repository_url" {
  description = "Docker repository URL, e.g. europe-west1-docker.pkg.dev/<project>/<repo>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "registry_host" {
  value = "${var.region}-docker.pkg.dev"
}
