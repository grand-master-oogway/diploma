# The Dagster VM: no external IP, SSH and UI only through IAP tunnels, runs as the given service account.
resource "google_compute_instance" "dagster" {
  name         = "${var.project_name}-${var.env}-dagster"
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type
  labels       = var.labels
  tags         = ["iap-access"]

  deletion_protection       = var.deletion_protection
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  # No access_config block: the instance gets no external IP.
  network_interface {
    subnetwork = var.subnetwork_self_link
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"] # actual access is limited by the service account's IAM roles
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # startup-script runs at every boot (installs Docker and the firms-run helper). Set as metadata (not
  # metadata_startup_script) so that changing it updates the VM in place instead of replacing it.
  metadata = merge(
    { enable-oslogin = "TRUE" },
    var.startup_script == null ? {} : { startup-script = var.startup_script },
  )
}
