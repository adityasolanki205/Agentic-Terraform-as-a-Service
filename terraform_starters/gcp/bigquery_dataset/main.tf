terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0, < 8.0"
    }
  }

  # The bucket name is supplied at init time. It must already exist.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}

resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.dataset_id
  location   = var.location

  # Deleting the dataset must not delete data inside it.
  delete_contents_on_destroy = false
}
