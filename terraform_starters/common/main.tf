terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 8.0"
    }
  }

  # The bucket name is supplied during terraform init. It must already exist.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}
