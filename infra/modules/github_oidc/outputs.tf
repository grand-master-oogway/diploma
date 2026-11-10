output "provider_name" {
  description = "Value for the WIF_PROVIDER GitHub variable."
  value       = google_iam_workload_identity_pool_provider.github.name
}
