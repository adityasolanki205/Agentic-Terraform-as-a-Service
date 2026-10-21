variable "project_id" {
  description = "Google Cloud project ID explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, start with a lowercase letter, and contain lowercase letters, numbers, or hyphens."
  }
}

variable "location" {
  description = "Google Cloud location explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?$", var.location))
    error_message = "Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}

# Resource-specific inputs live in one object. Each resource's .tf file reads
# only the keys it needs, while these common variables stay the same.
variable "resource_config" {
  description = "Settings for the one cloud resource requested by the user."
  type        = map(string)
}
