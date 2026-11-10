variable "project_id" {
  type = string
}

variable "project_name" {
  type    = string
  default = "firms-ua"
}

variable "env" {
  type = string
}

variable "github_repository" {
  type        = string
  description = "owner/name of the repository allowed to authenticate."
}

variable "github_repository_id" {
  type        = string
  description = "Numeric GitHub repository id (`gh api repos/<owner>/<name> --jq .id`); immutable, unlike the name."
}

variable "deploy_service_account_id" {
  type        = string
  description = "Resource name (projects/.../serviceAccounts/...) of the account used for deploys."
}

variable "plan_service_account_id" {
  type        = string
  description = "Resource name of the account used for terraform plan."
}
