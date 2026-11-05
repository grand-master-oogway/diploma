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

variable "buckets" {
  type        = map(string)
  description = "Layer name to bucket name (bronze, silver, gold, artifacts)."
}

variable "analyst_members" {
  type        = list(string)
  description = "IAM members (e.g. user:you@example.com) granted read on all buckets."
  default     = []
}
