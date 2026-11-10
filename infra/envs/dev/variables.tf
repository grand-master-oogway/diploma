variable "project_id" {
  type        = string
  description = "GCP project ID."
  default     = "nasa-firms"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "analyst_members" {
  type        = list(string)
  description = "Humans with read access, e.g. [\"user:you@example.com\"]."
  default     = []
}

variable "project_name" {
  type        = string
  description = "Prefix of bucket and resource names."
  default     = "firms-ua"
}

variable "github_repository" {
  type        = string
  description = "GitHub repository (owner/name) allowed to deploy."
  default     = "grand-master-oogway/diploma"
}

variable "github_repository_id" {
  type        = string
  description = "Numeric id of the GitHub repository (from the repository's OIDC subject)."
  default     = "1434867525"
}

variable "state_bucket" {
  type        = string
  description = "Terraform state bucket (created by hand, see infra/README.md)."
  default     = "nasa-firms-tfstate"
}
