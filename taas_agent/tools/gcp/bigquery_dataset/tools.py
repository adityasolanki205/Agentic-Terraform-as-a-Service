"""BigQuery dataset tool wrappers delegating to the generic TaaS engine.

Provides backward-compatible function signatures for any existing scripts or tests
while delegating directly to the unified generic tools.
"""

from ...tools import (
    _validate_inputs,
    apply_resource as apply_bigquery_dataset,
    generate_resource_files,
    get_request_status,
    plan_resource as plan_bigquery_dataset,
    verify_resource as verify_bigquery_dataset,
)


def validate_bigquery_dataset_request(
    project_id: str,
    dataset_id: str,
    location: str,
) -> dict:
    """Validate project ID, dataset ID, and location for BigQuery."""
    errors = _validate_inputs(project_id, location, dataset_id)
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {
        "status": "VALID",
        "project_id": project_id.strip(),
        "dataset_id": dataset_id.strip(),
        "location": location.strip(),
    }


def generate_bigquery_dataset_files(
    project_id: str,
    dataset_id: str,
    location: str,
) -> dict:
    """Generate BigQuery dataset Terraform artifacts using the generic engine."""
    return generate_resource_files(
        resource_type="gcp.bigquery_dataset",
        project_id=project_id,
        location=location,
        resource_name=dataset_id,
        config={"dataset_id": dataset_id},
    )


__all__ = [
    "validate_bigquery_dataset_request",
    "generate_bigquery_dataset_files",
    "plan_bigquery_dataset",
    "apply_bigquery_dataset",
    "verify_bigquery_dataset",
    "get_request_status",
]
