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

variable "zone" {
  type = string
}

variable "machine_type" {
  type    = string
  default = "e2-medium"
}

variable "disk_size_gb" {
  type    = number
  default = 50
}

variable "subnetwork_self_link" {
  type = string
}

variable "service_account_email" {
  type        = string
  description = "Service account the VM runs as (its IAM roles define what the pipeline can touch)."
}

variable "deletion_protection" {
  type    = bool
  default = false
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "startup_script" {
  type        = string
  description = "Bash script run at every boot."
  default     = null
}
