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
  type = string
}

variable "reader_members" {
  type        = list(string)
  description = "IAM members that may pull images (for example the VM's service account)."
  default     = []
}

variable "writer_members" {
  type        = list(string)
  description = "IAM members that may push images (for example the build service account)."
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}
