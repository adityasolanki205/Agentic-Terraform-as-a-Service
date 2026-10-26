"""Google Cloud Pub/Sub subscription tool wrappers delegating to the generic TaaS engine."""

from ...tools import (
    _validate_inputs,
    apply_resource as apply_pubsub_subscription,
    generate_resource_files,
    get_request_status,
    plan_resource as plan_pubsub_subscription,
    verify_resource as verify_pubsub_subscription,
)


def validate_pubsub_subscription_request(
    project_id: str,
    subscription_name: str,
    topic: str,
    location: str = "global",
) -> dict:
    """Validate project ID, subscription name, and parent topic for Pub/Sub subscription."""
    errors = _validate_inputs(project_id, location, subscription_name, resource_type="gcp.pubsub_subscription")
    topic_errors = _validate_inputs(project_id, location, topic, resource_type="gcp.pubsub_topic")
    for err in topic_errors:
        if "Resource name" in err or "Pub/Sub" in err:
            errors.append("Parent topic name must be a valid Pub/Sub topic name.")
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {
        "status": "VALID",
        "project_id": project_id.strip(),
        "subscription_name": subscription_name.strip(),
        "topic": topic.strip(),
        "location": location.strip(),
    }


def generate_pubsub_subscription_files(
    project_id: str,
    subscription_name: str,
    topic: str,
    location: str = "global",
    ack_deadline_seconds: int = 20,
) -> dict:
    """Generate Pub/Sub subscription Terraform artifacts using the generic engine."""
    clean_name = subscription_name.strip()
    clean_topic = topic.strip()
    return generate_resource_files(
        resource_type="gcp.pubsub_subscription",
        project_id=project_id,
        location=location,
        resource_name=clean_name,
        config={
            "subscription_name": clean_name,
            "topic": clean_topic,
            "ack_deadline_seconds": ack_deadline_seconds,
        },
    )


__all__ = [
    "validate_pubsub_subscription_request",
    "generate_pubsub_subscription_files",
    "plan_pubsub_subscription",
    "apply_pubsub_subscription",
    "verify_pubsub_subscription",
    "get_request_status",
]
