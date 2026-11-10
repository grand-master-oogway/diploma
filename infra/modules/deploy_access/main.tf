# What the deploy service account needs to reach one VM with `gcloud compute scp/ssh --tunnel-through-iap` and run sudo there.

# Log in through OS Login with administrator rights (the install script needs sudo) on this one instance.
resource "google_compute_instance_iam_member" "os_admin_login" {
  project       = var.project_id
  zone          = var.zone
  instance_name = var.instance_name
  role          = "roles/compute.osAdminLogin"
  member        = var.deploy_member
}

# Open the IAP tunnel to this one instance.
resource "google_iap_tunnel_instance_iam_member" "tunnel" {
  project  = var.project_id
  zone     = var.zone
  instance = var.instance_name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = var.deploy_member
}

# Logging in to a VM that runs as a service account requires permission to act as that account.
resource "google_service_account_iam_member" "act_as_vm_account" {
  service_account_id = var.vm_service_account_resource_id
  role               = "roles/iam.serviceAccountUser"
  member             = var.deploy_member
}

# gcloud reads project metadata while connecting (read-only).
resource "google_project_iam_member" "compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = var.deploy_member
}
