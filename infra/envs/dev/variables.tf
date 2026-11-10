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
