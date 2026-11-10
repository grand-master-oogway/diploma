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

# Values to set as GitHub Actions repository variables (Settings > Secrets and variables > Actions > Variables).
output "github_variables" {
  value = {
    GCP_PROJECT_ID         = var.project_id
    WIF_PROVIDER           = module.github_oidc.provider_name
    DEPLOY_SERVICE_ACCOUNT = module.iam.service_account_emails["deploy"]
    WIF_SERVICE_ACCOUNT    = module.iam.service_account_emails["plan"]
    TF_STATE_BUCKET        = var.state_bucket
  }
}
