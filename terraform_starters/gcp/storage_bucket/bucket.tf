# Google Cloud Storage bucket resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/bucket.tf.
resource "google_storage_bucket" "requested" {
  name                        = var.resource_config["bucket_name"]
  project                     = var.project_id
  location                    = var.location
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = lookup(var.resource_config, "versioning", true)
  }
}
