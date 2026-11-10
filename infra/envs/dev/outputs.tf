output "buckets" {
  value = module.storage.bucket_names
}

output "service_accounts" {
  value = module.iam.service_account_emails
}

output "map_key_secret_id" {
  value = module.secrets.map_key_secret_id
}

output "dagster_vm" {
  value = { name = module.vm.instance_name, zone = module.vm.zone }
}
