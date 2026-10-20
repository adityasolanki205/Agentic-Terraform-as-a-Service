variable "project_id" {
  description = "Google Cloud project ID explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, start with a lowercase letter, and contain lowercase letters, numbers, or hyphens."
  }
}

variable "dataset_id" {
  description = "BigQuery dataset ID explicitly requested by the user."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]{0,1023}$", var.dataset_id))
    error_message = "Dataset ID must start with a letter or underscore and contain only letters, numbers, or underscores."
  }
}

variable "location" {
  description = "BigQuery dataset location explicitly provided for this request."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9]([A-Za-z0-9-]{0,62}[A-Za-z0-9])?$", var.location))
    error_message = "Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen."
  }
}
