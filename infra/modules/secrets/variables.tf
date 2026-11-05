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

variable "accessor_members" {
  type        = list(string)
  description = "IAM members allowed to read the MAP_KEY secret."
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}
