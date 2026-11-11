# Lets GitHub Actions of one repository act as Google service accounts without any stored key.
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.project_name}-${var.env}-github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  # GitHub signs the owner and repo IDs into the `sub` claim of this repository (immutable subject), so bindings cannot rely on
  # `sub` being `repo:owner/name:...`. repo_ref combines the immutable repository ID with the git ref instead.
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.repo_ref"   = "assertion.repository_id + ':' + assertion.ref"
  }

  # Tokens from any other repository (or a recreated repository with the same name) are refused outright.
  attribute_condition = "assertion.repository == \"${var.github_repository}\" && assertion.repository_id == \"${var.github_repository_id}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Deploy (push images): only runs of the main branch may use it.
resource "google_service_account_iam_member" "deploy" {
  service_account_id = var.deploy_service_account_id
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repo_ref/${var.github_repository_id}:refs/heads/main"
}

# Terraform apply: only runs of the main branch (after merge). The workflow job also waits for approval in a GitHub environment.
resource "google_service_account_iam_member" "apply" {
  service_account_id = var.apply_service_account_id
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repo_ref/${var.github_repository_id}:refs/heads/main"
}

# Terraform plan (read-only): any run of the repository, including pull requests.
resource "google_service_account_iam_member" "plan" {
  service_account_id = var.plan_service_account_id
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
