"""Google Cloud Storage bucket tool wrappers delegating to the generic TaaS engine."""

from ...tools import (
    _validate_inputs,
    apply_resource as apply_storage_bucket,
    generate_resource_files,
    get_request_status,
    plan_resource as plan_storage_bucket,
    verify_resource as verify_storage_bucket,
)


def validate_storage_bucket_request(
    project_id: str,
    bucket_name: str,
    location: str = "asia-south2",
) -> dict:
    """Validate project ID, bucket name, and location for GCS bucket."""
    errors = _validate_inputs(project_id, location, bucket_name, resource_type="gcp.storage_bucket")
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {
        "status": "VALID",
        "project_id": project_id.strip(),
        "bucket_name": bucket_name.strip().lower(),
        "location": location.strip(),
    }


def generate_storage_bucket_files(
    project_id: str,
    bucket_name: str,
    location: str = "asia-south2",
    versioning: bool = True,
) -> dict:
    """Generate GCS bucket Terraform artifacts using the generic engine."""
    clean_name = bucket_name.strip().lower()
    return generate_resource_files(
        resource_type="gcp.storage_bucket",
        project_id=project_id,
        location=location,
        resource_name=clean_name,
        config={"bucket_name": clean_name, "versioning": versioning},
    )


__all__ = [
    "validate_storage_bucket_request",
    "generate_storage_bucket_files",
    "plan_storage_bucket",
    "apply_storage_bucket",
    "verify_storage_bucket",
    "get_request_status",
]
