output "instance_name" {
  value = google_compute_instance.dagster.name
}

output "zone" {
  value = google_compute_instance.dagster.zone
}
