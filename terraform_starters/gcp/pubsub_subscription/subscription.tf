# Google Cloud Pub/Sub subscription resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/subscription.tf.
resource "google_pubsub_subscription" "requested" {
  name                       = var.resource_config["subscription_name"]
  topic                      = var.resource_config["topic"]
  project                    = var.project_id
  message_retention_duration = "604800s"
  retain_acked_messages      = false
  ack_deadline_seconds       = 20
}
