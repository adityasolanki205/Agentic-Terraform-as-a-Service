# This file contains the BigQuery dataset resource itself. Shared Terraform
# setup and shared variables are in terraform_starters/common/.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
  
}
