# BigQuery dataset resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/dataset.tf.
resource "google_bigquery_dataset" "requested" {
  project    = var.project_id
  dataset_id = var.resource_config["dataset_id"]
  location   = var.location
}
