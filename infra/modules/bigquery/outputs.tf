output "datasets" {
  description = "Layer name to BigQuery dataset id."
  value       = { for k, d in google_bigquery_dataset.layer : k => d.dataset_id }
}

output "tables" {
  description = "Fully qualified external tables (project.dataset.table)."
  value       = [for t in google_bigquery_table.external : "${t.project}.${t.dataset_id}.${t.table_id}"]
}

output "connection_service_account" {
  description = "Service account BigQuery uses to read the buckets."
  value       = google_bigquery_connection.lake.cloud_resource[0].service_account_id
}
