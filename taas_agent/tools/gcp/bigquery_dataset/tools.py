"""Deterministic tools for the BigQuery dataset provisioning workflow.

The language model can choose when to call these tools, but it cannot provide
Terraform source or shell commands. Terraform commands below are fixed and are
always run against files copied from the reviewed starter.
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


# This file is nested under taas_agent/tools/gcp/bigquery_dataset.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
COMMON_STARTER_DIR = PROJECT_ROOT / "terraform_starters" / "common"
RESOURCE_STARTER_FILE = (
    PROJECT_ROOT
    / "terraform_starters"
    / "gcp"
    / "bigquery_dataset"
    / "bigquery_dataset.tf"
)
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REQUESTS_DIR = PROJECT_ROOT / ".taas" / "requests"

EXPECTED_RESOURCE_ADDRESS = "google_bigquery_dataset.requested"
PLAN_RETRY_WINDOW_SECONDS = 600
VERIFY_ATTEMPTS = 6
VERIFY_DELAY_SECONDS = 5


def _now() -> str:
    """Return a UTC timestamp suitable for a local request record."""
    return datetime.now(timezone.utc).isoformat()


def _request_record_path(request_id: str) -> Path:
    """Build a safe request-record path from a UUID, not a user path."""
    try:
        safe_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Request ID is invalid.") from exc
    return REQUESTS_DIR / safe_id / "request.json"


def _save_record(record: dict) -> None:
    """Write request progress locally using an atomic file replacement."""
    path = _request_record_path(record["request_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    record["updated_at"] = _now()
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _load_record(request_id: str) -> dict:
    """Read the local record for a previously generated request."""
    path = _request_record_path(request_id)
    if not path.is_file():
        raise FileNotFoundError(
            "No request record was found. Generate the Terraform artifacts first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _set_status(record: dict, status: str, message: str) -> None:
    """Save a clear lifecycle status for the user and later tool calls."""
    record["status"] = status
    record["status_message"] = message
    _save_record(record)


def _validate_values(
    project_id: str,
    dataset_id: str,
    location: str,
) -> tuple[dict, list[str]]:
    """Normalize and validate values shared by the public request tools."""
    project_id = project_id.strip()
    dataset_id = dataset_id.strip()
    location = location.strip()
    errors = []

    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id):
        errors.append(
            "Project ID must be 6-30 characters, start with a lowercase "
            "letter, and contain lowercase letters, numbers, or hyphens."
        )

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,1023}", dataset_id):
        errors.append(
            "Dataset ID must start with a letter or underscore and contain "
            "only letters, numbers, or underscores."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?",
        location,
    ):
        errors.append(
            "Location must contain letters, numbers, or hyphens and cannot "
            "start or end with a hyphen."
        )

    return {
        "project_id": project_id,
        "dataset_id": dataset_id,
        "location": location,
    }, errors


def validate_bigquery_dataset_request(
    project_id: str,
    dataset_id: str,
    location: str,
) -> dict:
    """Validate the three values required to create one BigQuery dataset.

    Ask the user for all three values before calling this tool. It performs
    local format checks only and does not contact Google Cloud.
    """
    values, errors = _validate_values(project_id, dataset_id, location)
    if errors:
        return {"status": "INVALID", "errors": errors}
    return {"status": "VALID", **values}


def generate_bigquery_dataset_files(
    project_id: str,
    dataset_id: str,
    location: str,
) -> dict:
    """Copy the approved Terraform starter and fill in request values.

    Call only after collecting the project ID, dataset ID, and location.
    Copies shared main.tf and variables.tf, then adds the BigQuery dataset
    resource file and request values under a unique artifacts/ folder. Does
    not execute Terraform or contact Google Cloud.
    """
    values, errors = _validate_values(project_id, dataset_id, location)
    if errors:
        return {"status": "INVALID", "errors": errors}

    starter_files = [
        COMMON_STARTER_DIR / "main.tf",
        COMMON_STARTER_DIR / "variables.tf",
        RESOURCE_STARTER_FILE,
    ]
    missing = [str(path) for path in starter_files if not path.is_file()]
    if missing:
        return {
            "status": "ERROR",
            "message": "Missing approved Terraform starter file(s): "
            + ", ".join(missing),
        }

    request_id = str(uuid4())
    output_dir = ARTIFACTS_DIR / f"bigquery-dataset-{request_id}"
    output_dir.mkdir(parents=True, exist_ok=False)

    for starter in starter_files:
        # Shared files stay named main.tf/variables.tf in every generated root.
        # Each resource starter keeps a distinct filename for easy review.
        shutil.copy2(starter, output_dir / starter.name)

    # JSON string quoting is compatible with Terraform's quoted string values.
    tfvars_content = (
        f"project_id = {json.dumps(values['project_id'])}\n"
        f"location   = {json.dumps(values['location'])}\n"
        "resource_config = {\n"
        f"  dataset_id = {json.dumps(values['dataset_id'])}\n"
        "}\n"
    )
    (output_dir / "terraform.tfvars").write_text(
        tfvars_content,
        encoding="utf-8",
    )

    record = {
        "request_id": request_id,
        "resource_type": "gcp.bigquery_dataset",
        **values,
        "status": "ARTIFACTS_READY",
        "status_message": "Terraform artifacts are ready for review.",
        "artifact_directory": str(output_dir.resolve()),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save_record(record)

    return {
        "status": "SUCCESS",
        "request_id": request_id,
        "artifact_directory": str(output_dir.resolve()),
        "files": [
            str(output_dir / "main.tf"),
            str(output_dir / "variables.tf"),
            str(output_dir / "bigquery_dataset.tf"),
            str(output_dir / "terraform.tfvars"),
        ],
        "message": (
            "Terraform artifacts are ready for review. No Terraform commands "
            "were run and no cloud resources were created."
        ),
    }


def _run_terraform(args: list[str], working_directory: Path) -> dict:
    """Run one fixed Terraform command without invoking a shell."""
    terraform_path = shutil.which("terraform")
    if not terraform_path:
        return {
            "returncode": 127,
            "output": "Terraform was not found. Install Terraform and try again.",
        }

    command = [terraform_path, *args]
    try:
        result = subprocess.run(
            command,
            cwd=str(working_directory),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=PLAN_RETRY_WINDOW_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "returncode": 124,
            "output": "Terraform command timed out after 10 minutes.",
        }
    except OSError as exc:
        return {"returncode": 1, "output": f"Could not start Terraform: {exc}"}

    return {"returncode": result.returncode, "output": result.stdout or ""}


def _get_state_bucket(project_id: str) -> tuple[str | None, str | None]:
    """Require an existing, versioned GCS bucket; never create or edit it."""
    bucket_name = os.getenv("TAAS_STATE_BUCKET", "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket_name):
        return None, (
            "TAAS_STATE_BUCKET is not set to a valid existing bucket name. "
            "Ask the user to configure an approved state bucket before planning."
        )

    try:
        from google.cloud import storage

        bucket = storage.Client(project=project_id).get_bucket(bucket_name)
    except Exception as exc:  # Google SDK errors need a readable tool response.
        return None, (
            f"Could not inspect GCS bucket {bucket_name!r}: {exc}. "
            "Confirm that the bucket exists and the current credentials can read it."
        )

    if not bucket.versioning_enabled:
        return None, (
            f"GCS bucket {bucket_name!r} does not have object versioning enabled. "
            "Enable versioning through the approved setup process before planning."
        )

    return bucket_name, None


def _artifact_directory(record: dict) -> Path:
    """Resolve a generated artifact path and keep it inside artifacts/."""
    artifact_dir = Path(record["artifact_directory"]).resolve()
    artifacts_root = ARTIFACTS_DIR.resolve()
    if not artifact_dir.is_relative_to(artifacts_root):
        raise ValueError("Request artifact path is outside the artifacts folder.")
    if not artifact_dir.is_dir():
        raise FileNotFoundError("Generated Terraform artifact folder is missing.")
    return artifact_dir


def _workspace_is_default(working_directory: Path) -> tuple[bool, str]:
    """Check that the run uses Terraform's single default workspace."""
    result = _run_terraform(["workspace", "show"], working_directory)
    if result["returncode"] != 0:
        return False, result["output"]
    workspace = result["output"].strip()
    if workspace != "default":
        return False, (
            f"Current Terraform workspace is {workspace!r}; only the default "
            "workspace is supported."
        )
    return True, workspace


def plan_bigquery_dataset(request_id: str) -> dict:
    """Format, initialize, validate, and plan a generated dataset request.

    Requires TAAS_STATE_BUCKET to name an existing versioned GCS bucket.
    Uses one default Terraform state under prefix taas/<project-id>. The plan
    is rejected if it proposes any resource change besides creating the one
    requested BigQuery dataset. This tool does not apply the plan.
    """
    try:
        record = _load_record(request_id)
        working_directory = _artifact_directory(record)
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "message": str(exc)}

    bucket_name, bucket_error = _get_state_bucket(record["project_id"])
    if bucket_error:
        return {"status": "BLOCKED", "message": bucket_error}

    _set_status(record, "PLANNING", "Terraform plan is being prepared.")

    steps = [
        ("format", ["fmt", "-recursive"]),
        (
            "initialize",
            [
                "init",
                "-input=false",
                f"-backend-config=bucket={bucket_name}",
                f"-backend-config=prefix=taas/{record['project_id']}",
            ],
        ),
    ]
    for step_name, args in steps:
        result = _run_terraform(args, working_directory)
        if result["returncode"] != 0:
            _set_status(record, "PLAN_FAILED", f"Terraform {step_name} failed.")
            return {
                "status": "ERROR",
                "step": step_name,
                "message": result["output"][-12000:],
            }

    is_default, workspace_result = _workspace_is_default(working_directory)
    if not is_default:
        _set_status(record, "BLOCKED", "Only the default workspace is supported.")
        return {"status": "BLOCKED", "message": workspace_result}

    for step_name, args in [
        ("validate", ["validate", "-no-color"]),
    ]:
        result = _run_terraform(args, working_directory)
        if result["returncode"] != 0:
            _set_status(record, "PLAN_FAILED", f"Terraform {step_name} failed.")
            return {
                "status": "ERROR",
                "step": step_name,
                "message": result["output"][-12000:],
            }

    private_dir = _request_record_path(request_id).parent
    private_dir.mkdir(parents=True, exist_ok=True)
    saved_plan = private_dir / "terraform.tfplan"
    saved_plan.unlink(missing_ok=True)

    result = _run_terraform(
        [
            "plan",
            "-input=false",
            "-no-color",
            "-lock-timeout=5m",
            f"-out={saved_plan}",
        ],
        working_directory,
    )
    if result["returncode"] != 0:
        _set_status(record, "PLAN_FAILED", "Terraform plan failed.")
        return {"status": "ERROR", "step": "plan", "message": result["output"][-16000:]}

    readable_plan = _run_terraform(
        ["show", "-no-color", str(saved_plan)],
        working_directory,
    )
    if readable_plan["returncode"] != 0:
        _set_status(record, "PLAN_FAILED", "Terraform could not display the plan.")
        return {
            "status": "ERROR",
            "step": "show plan",
            "message": readable_plan["output"][-12000:],
        }

    json_plan = _run_terraform(
        ["show", "-json", str(saved_plan)],
        working_directory,
    )
    if json_plan["returncode"] != 0:
        _set_status(record, "PLAN_FAILED", "Terraform could not inspect the plan.")
        return {
            "status": "ERROR",
            "step": "inspect plan",
            "message": json_plan["output"][-12000:],
        }

    try:
        plan_data = json.loads(json_plan["output"])
    except json.JSONDecodeError:
        _set_status(record, "PLAN_FAILED", "Terraform returned unreadable plan data.")
        return {"status": "ERROR", "message": "Terraform returned invalid plan JSON."}

    unexpected_changes = []
    for change in plan_data.get("resource_changes", []):
        address = change.get("address", "unknown")
        actions = change.get("change", {}).get("actions", [])
        if actions == ["no-op"]:
            continue
        if address != EXPECTED_RESOURCE_ADDRESS or actions != ["create"]:
            unexpected_changes.append({"address": address, "actions": actions})

    if unexpected_changes:
        _set_status(
            record,
            "BLOCKED_PLAN",
            "The plan includes changes outside the one requested dataset creation.",
        )
        return {
            "status": "BLOCKED",
            "message": (
                "The plan contains an update, deletion, or additional resource "
                "change, so it cannot be applied."
            ),
            "unexpected_changes": unexpected_changes,
            "plan_summary": readable_plan["output"][:30000],
        }

    digest = hashlib.sha256(saved_plan.read_bytes()).hexdigest()
    record["plan_sha256"] = digest
    record["plan_file"] = str(saved_plan.resolve())
    record["plan_summary"] = readable_plan["output"]
    _set_status(
        record,
        "AWAITING_APPROVAL",
        "Plan is ready. Review it before approving apply.",
    )

    return {
        "status": "AWAITING_APPROVAL",
        "request_id": request_id,
        "plan_sha256": digest,
        "plan_summary": readable_plan["output"][:30000],
        "message": (
            "Review this plan. It will not be applied until you explicitly "
            "approve the apply tool call."
        ),
    }


def apply_bigquery_dataset(request_id: str, plan_sha256: str) -> dict:
    """Apply the exact saved plan after ADK's confirmation gate is approved.

    Register this function only through FunctionTool with
    require_confirmation=True. It checks that the saved plan still matches
    the digest shown to the user, then applies that plan file without creating
    a new plan.
    """
    try:
        record = _load_record(request_id)
        working_directory = _artifact_directory(record)
        # Derive the plan path from the request UUID instead of trusting a
        # filesystem path stored in the local JSON record.
        saved_plan = _request_record_path(request_id).parent / "terraform.tfplan"
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "message": str(exc)}

    if record.get("status") != "AWAITING_APPROVAL":
        return {
            "status": "BLOCKED",
            "message": "This request does not have a plan awaiting approval.",
        }

    if plan_sha256 != record.get("plan_sha256"):
        return {
            "status": "BLOCKED",
            "message": "The plan digest does not match the plan shown for approval.",
        }

    if not saved_plan.is_file():
        return {"status": "ERROR", "message": "The saved Terraform plan is missing."}

    actual_digest = hashlib.sha256(saved_plan.read_bytes()).hexdigest()
    if actual_digest != plan_sha256:
        return {
            "status": "BLOCKED",
            "message": "The saved plan changed after review. Generate and review a new plan.",
        }

    is_default, workspace_result = _workspace_is_default(working_directory)
    if not is_default:
        _set_status(record, "BLOCKED", "Only the default workspace is supported.")
        return {"status": "BLOCKED", "message": workspace_result}

    _set_status(record, "APPLYING", "The approved Terraform plan is being applied.")
    result = _run_terraform(
        [
            "apply",
            "-input=false",
            "-no-color",
            "-lock-timeout=5m",
            str(saved_plan),
        ],
        working_directory,
    )

    if result["returncode"] != 0:
        _set_status(record, "APPLY_FAILED", "Terraform apply failed.")
        return {
            "status": "ERROR",
            "step": "apply",
            "message": result["output"][-16000:],
        }

    record["apply_summary"] = result["output"]
    _set_status(record, "VERIFYING", "Apply completed; resource verification is next.")
    return {
        "status": "APPLIED",
        "request_id": request_id,
        "message": (
            "Terraform apply completed. The dataset is not reported ready "
            "until the verification tool confirms it exists."
        ),
        "apply_summary": result["output"][-12000:],
    }


async def verify_bigquery_dataset(request_id: str) -> dict:
    """Asynchronously check that the applied dataset exists in the right place.

    Call after apply. The tool retries for up to 30 seconds. If the API has
    not confirmed the dataset by then, it returns VERIFYING; do not tell the
    user the resource is ready in that case.
    """
    try:
        record = _load_record(request_id)
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "message": str(exc)}

    if record.get("status") == "READY":
        return {
            "status": "READY",
            "message": "The BigQuery dataset has already been verified.",
        }
    if record.get("status") not in {"VERIFYING", "APPLIED"}:
        return {
            "status": "BLOCKED",
            "message": "Apply must complete successfully before verification.",
        }

    try:
        from google.api_core.exceptions import NotFound
        from google.cloud import bigquery

        client = bigquery.Client(project=record["project_id"])
    except Exception as exc:
        _set_status(record, "VERIFYING", "Waiting for BigQuery verification access.")
        return {"status": "ERROR", "message": f"Could not start verification: {exc}"}

    _set_status(record, "VERIFYING", "Checking whether the dataset is ready.")
    dataset_name = f"{record['project_id']}.{record['dataset_id']}"

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        try:
            dataset = await asyncio.to_thread(client.get_dataset, dataset_name)
            if dataset.location.casefold() != record["location"].casefold():
                _set_status(
                    record,
                    "VERIFICATION_FAILED",
                    "Dataset exists, but its location does not match the request.",
                )
                return {
                    "status": "ERROR",
                    "message": (
                        f"Dataset was found in {dataset.location}, but the request "
                        f"specified {record['location']}."
                    ),
                }

            _set_status(
                record,
                "READY",
                "BigQuery confirmed the dataset exists in the requested location.",
            )
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "dataset_id": record["dataset_id"],
                "location": dataset.location,
                "message": "The BigQuery dataset is ready.",
            }
        except NotFound:
            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)
        except Exception as exc:
            _set_status(record, "VERIFYING", "BigQuery verification needs another attempt.")
            return {
                "status": "ERROR",
                "message": f"BigQuery verification could not complete: {exc}",
            }

    _set_status(
        record,
        "VERIFYING",
        "Dataset was not visible during this check; verification can be retried.",
    )
    return {
        "status": "VERIFYING",
        "request_id": request_id,
        "message": (
            "The dataset has not been confirmed yet. It is not ready until "
            "a later verification succeeds."
        ),
    }


def get_request_status(request_id: str) -> dict:
    """Return the saved status for a TaaS request."""
    try:
        record = _load_record(request_id)
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        return {"status": "ERROR", "message": str(exc)}

    return {
        "status": record.get("status", "UNKNOWN"),
        "request_id": record["request_id"],
        "resource_type": record.get("resource_type"),
        "project_id": record.get("project_id"),
        "dataset_id": record.get("dataset_id"),
        "location": record.get("location"),
        "status_message": record.get("status_message"),
        "updated_at": record.get("updated_at"),
    }
