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

variable "region" {
  type        = string
  description = "Location of the datasets and the connection; must match the buckets' location."
}

variable "buckets" {
  type        = map(string)
  description = "Layer name to bucket name (at least every layer that has a spec in schemas/)."
}

variable "analyst_members" {
  type        = list(string)
  description = "IAM members (e.g. user:you@example.com) allowed to query the datasets."
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}
