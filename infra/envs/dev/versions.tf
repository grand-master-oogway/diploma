terraform {
  required_version = ">= 1.9, < 2.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Bucket is passed at init time: terraform init -backend-config="bucket=<state-bucket>"
  backend "gcs" {
    prefix = "firms-ua/dev"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
