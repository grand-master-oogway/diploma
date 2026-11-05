output "bucket_names" {
  description = "Layer name to bucket name."
  value       = { for k, b in google_storage_bucket.layer : k => b.name }
}
