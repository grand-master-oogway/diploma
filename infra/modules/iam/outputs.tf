output "service_account_emails" {
  description = "Component name to service account email."
  value       = { for k, sa in google_service_account.component : k => sa.email }
}

output "service_account_members" {
  description = "Component name to IAM member string."
  value       = { for k, sa in google_service_account.component : k => sa.member }
}
