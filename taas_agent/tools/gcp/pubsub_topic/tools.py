"""Google Cloud Pub/Sub topic tool wrappers delegating to the generic TaaS engine."""

from ...tools import (
    _validate_inputs,
    apply_resource as apply_pubsub_topic,
    generate_resource_files,
    get_request_status,
    plan_resource as plan_pubsub_topic,
    verify_resource as verify_pubsub_topic,
)


def validate_pubsub_topic_request(
    project_id: str,
    topic_name: str,
    location: str = "global",
) -> dict:
    """Validate project ID and topic name for Pub/Sub topic."""
    errors = _validate_inputs(project_id, location, topic_name, resource_type="gcp.pubsub_topic")
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {
        "status": "VALID",
        "project_id": project_id.strip(),
        "topic_name": topic_name.strip(),
        "location": location.strip(),
    }


def generate_pubsub_topic_files(
    project_id: str,
    topic_name: str,
    location: str = "global",
) -> dict:
    """Generate Pub/Sub topic Terraform artifacts using the generic engine."""
    clean_name = topic_name.strip()
    return generate_resource_files(
        resource_type="gcp.pubsub_topic",
        project_id=project_id,
        location=location,
        resource_name=clean_name,
        config={"topic_name": clean_name},
    )


__all__ = [
    "validate_pubsub_topic_request",
    "generate_pubsub_topic_files",
    "plan_pubsub_topic",
    "apply_pubsub_topic",
    "verify_pubsub_topic",
    "get_request_status",
]
