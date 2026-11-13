# Google Cloud SQL database instance resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/sql.tf.
resource "google_sql_database_instance" "requested" {
  name                = var.resource_config["instance_name"]
  project             = var.project_id
  region              = var.location
  database_version    = lookup(var.resource_config, "database_version", "POSTGRES_15")
  deletion_protection = false

  settings {
    tier              = lookup(var.resource_config, "tier", "db-f1-micro")
    availability_type = "ZONAL"
    disk_autoresize   = true
    disk_size         = 10
    disk_type         = "PD_SSD"
  }
}

