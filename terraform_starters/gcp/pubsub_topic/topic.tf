# Google Cloud Pub/Sub topic resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/topic.tf.
resource "google_pubsub_topic" "requested" {
  name    = var.resource_config["topic_name"]
  project = var.project_id
}
