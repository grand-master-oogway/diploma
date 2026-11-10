resource "google_compute_network" "vpc" {
  name                    = "${var.project_name}-${var.env}"
  project                 = var.project_id
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name                     = "${var.project_name}-${var.env}-${var.region}"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true # reach Google APIs (GCS, Secret Manager) without external IPs
}

resource "google_compute_router" "router" {
  name    = "${var.project_name}-${var.env}-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.vpc.id
}

# Outbound internet (FIRMS API) for VMs that have no external IP.
resource "google_compute_router_nat" "nat" {
  name                               = "${var.project_name}-${var.env}-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.router.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# Only the IAP range may reach SSH and the Dagster UI port; there is no public ingress.
resource "google_compute_firewall" "iap" {
  name      = "${var.project_name}-${var.env}-allow-iap"
  project   = var.project_id
  network   = google_compute_network.vpc.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["iap-access"]

  allow {
    protocol = "tcp"
    ports    = ["22", "3000"]
  }
}
