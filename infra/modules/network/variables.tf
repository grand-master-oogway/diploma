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

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/24"
}
