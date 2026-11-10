variable "project_id" {
  type = string
}

variable "zone" {
  type = string
}

variable "instance_name" {
  type = string
}

variable "deploy_member" {
  type        = string
  description = "IAM member string of the deploy service account (serviceAccount:...)."
}

variable "vm_service_account_resource_id" {
  type        = string
  description = "Resource name (projects/.../serviceAccounts/...) of the account the VM runs as."
}
