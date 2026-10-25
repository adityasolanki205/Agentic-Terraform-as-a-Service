"""BigQuery table tool wrappers delegating to the generic TaaS engine.

Provides backward-compatible function signatures for any existing scripts or tests
while delegating directly to the unified generic tools.
"""

from ...tools import (
    _validate_inputs,
    apply_resource as apply_bigquery_table,
    generate_resource_files,
    get_request_status,
    plan_resource as plan_bigquery_table,
    verify_resource as verify_bigquery_table,
)


import json


def validate_bigquery_table_request(
    project_id: str,
    dataset_id: str,
    table_id: str,
    location: str,
    schema: str | None = None,
) -> dict:
    """Validate project ID, dataset ID, table ID, location, and optional schema for BigQuery table."""
    errors = _validate_inputs(project_id, location, table_id)
    dataset_errors = _validate_inputs(project_id, location, dataset_id)
    for err in dataset_errors:
        if "Resource name" in err:
            errors.append("Dataset ID must contain only letters, numbers, or underscores.")
    if schema and schema.strip().lower() not in ("none", "null", "skip", "no"):
        try:
            parsed = json.loads(schema) if isinstance(schema, str) else schema
            if not isinstance(parsed, (list, dict)):
                errors.append("BigQuery table schema must be a JSON array of column definitions (e.g. '[{\"name\": \"id\", \"type\": \"STRING\"}]').")
        except Exception as exc:
            errors.append(f"BigQuery table schema must be valid JSON: {exc}")
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {
        "status": "VALID",
        "project_id": project_id.strip(),
        "dataset_id": dataset_id.strip(),
        "table_id": table_id.strip(),
        "location": location.strip(),
        "has_schema": bool(schema and schema.strip().lower() not in ("none", "null", "skip", "no")),
    }


def generate_bigquery_table_files(
    project_id: str,
    dataset_id: str,
    table_id: str,
    location: str,
    schema: str | None = None,
) -> dict:
    """Generate BigQuery table Terraform artifacts using the generic engine."""
    config = {"dataset_id": dataset_id.strip(), "table_id": table_id.strip()}
    if schema:
        config["schema"] = schema
    return generate_resource_files(
        resource_type="gcp.bigquery_table",
        project_id=project_id,
        location=location,
        resource_name=table_id,
        config=config,
    )


__all__ = [
    "validate_bigquery_table_request",
    "generate_bigquery_table_files",
    "plan_bigquery_table",
    "apply_bigquery_table",
    "verify_bigquery_table",
    "get_request_status",
]
