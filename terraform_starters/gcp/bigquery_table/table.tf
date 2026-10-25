# BigQuery table resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/table.tf.
resource "google_bigquery_table" "requested" {
  project             = var.project_id
  dataset_id          = var.resource_config["dataset_id"]
  table_id            = var.resource_config["table_id"]
  deletion_protection = false

  schema = lookup(var.resource_config, "schema", null)
}
