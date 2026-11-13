# Google Compute Engine VM instance resource template.
# Sourced at runtime to render resource blocks into artifacts/gcp/compute.tf.
resource "google_compute_instance" "requested" {
  name                      = var.resource_config["instance_name"]
  machine_type              = lookup(var.resource_config, "machine_type", "e2-micro")
  zone                      = lookup(var.resource_config, "zone", "${var.location}-a")
  project                   = var.project_id
  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }
}

