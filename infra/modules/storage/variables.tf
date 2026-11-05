variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "project_name" {
  type        = string
  description = "Short project name used in bucket names."
  default     = "firms-ua"
}

variable "env" {
  type        = string
  description = "Environment name (dev or prod)."
}

variable "region" {
  type        = string
  description = "Single bucket region, e.g. europe-west1."
}

variable "force_destroy" {
  type        = bool
  description = "Allow deleting non-empty buckets. Keep false outside throwaway dev."
  default     = false
}

variable "bronze_coldline_after_days" {
  type    = number
  default = 90
}

variable "noncurrent_expire_days" {
  type    = number
  default = 30
}

variable "labels" {
  type    = map(string)
  default = {}
}
