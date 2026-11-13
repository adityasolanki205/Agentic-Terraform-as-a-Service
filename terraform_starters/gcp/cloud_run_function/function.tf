# Google Cloud Run Function (2nd Gen) resource template with Python Hello World source.
# Sourced at runtime to render resource blocks into artifacts/gcp/function.tf.
resource "google_cloudfunctions2_function" "requested" {
  name        = var.resource_config["function_name"]
  location    = var.location
  project     = var.project_id
  description = "Python Hello World Cloud Run Function managed by TaaS"

  build_config {
    runtime     = "python312"
    entry_point = "hello_http"
    source {
      storage_source {
        bucket = var.resource_config["source_bucket"]
        object = var.resource_config["source_object"]
      }
    }
  }

  service_config {
    max_instance_count = 3
    available_memory   = "256M"
    timeout_seconds    = 60
  }
}

