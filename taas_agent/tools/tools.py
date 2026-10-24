"""Generic deterministic tools for Terraform-as-a-Service (TaaS).

These tools are cloud- and resource-agnostic. They support the full resource lifecycle:
- Generation from reviewed Terraform starters
- Terraform planning with strict AST change-set inspection
- Apply gated by explicit user confirmation
- Safe resource deactivation (commenting out .tf files and applying destroy)
- Seamless recreation (uncommenting .tf files and applying create)
- Post-apply cloud verification and status tracking
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMON_STARTER_DIR = PROJECT_ROOT / "terraform_starters" / "common"
STARTERS_DIR = PROJECT_ROOT / "terraform_starters"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REQUESTS_DIR = PROJECT_ROOT / ".taas" / "requests"

PLAN_TIMEOUT_SECONDS = 600
VERIFY_ATTEMPTS = 6
VERIFY_DELAY_SECONDS = 5


# Registry of supported resources mapping to their starter directories and expected addresses.
SUPPORTED_RESOURCES = {
    "gcp.bigquery_dataset": {
        "provider": "gcp",
        "short_name": "bigquery_dataset",
        "starter_dir": STARTERS_DIR / "gcp" / "bigquery_dataset",
        "primary_tf": "bigquery_dataset.tf",
        "expected_address": "google_bigquery_dataset.requested",
        "name_param": "dataset_id",
        "description": "Google Cloud BigQuery Dataset",
    },
}


def _now() -> str:
    """Return a UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_resource_type(resource_type: str) -> str:
    """Normalize resource type names (e.g. 'bigquery_dataset' -> 'gcp.bigquery_dataset')."""
    cleaned = resource_type.strip().lower()
    if cleaned in SUPPORTED_RESOURCES:
        return cleaned
    for key, spec in SUPPORTED_RESOURCES.items():
        if cleaned == spec["short_name"] or cleaned.endswith(f".{spec['short_name']}"):
            return key
    return cleaned


def _request_record_path(request_id: str) -> Path:
    """Build a safe request-record path from a UUID."""
    try:
        safe_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Request ID '{request_id}' is invalid.") from exc
    return REQUESTS_DIR / safe_id / "request.json"


def _save_record(record: dict) -> None:
    """Write request progress locally using an atomic file replacement."""
    path = _request_record_path(record["request_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    record["updated_at"] = _now()
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def _load_record(request_id: str) -> dict:
    """Read the local record for a previously generated request."""
    path = _request_record_path(request_id)
    if not path.is_file():
        raise FileNotFoundError(f"No request record found for ID: {request_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _set_status(record: dict, status: str, message: str) -> None:
    """Update status and persist the record."""
    record["status"] = status
    record["status_message"] = message
    _save_record(record)


def _find_records(
    project_id: str | None = None,
    resource_name: str | None = None,
    resource_type: str | None = None,
) -> list[dict]:
    """Search existing request records matching filters."""
    results = []
    if not REQUESTS_DIR.exists():
        return results

    for item in REQUESTS_DIR.iterdir():
        rec_file = item / "request.json"
        if rec_file.is_file():
            try:
                rec = json.loads(rec_file.read_text(encoding="utf-8"))
                if project_id and rec.get("project_id") != project_id:
                    continue
                if resource_name and rec.get("resource_name") != resource_name:
                    continue
                if resource_type and rec.get("resource_type") != _normalize_resource_type(resource_type):
                    continue
                results.append(rec)
            except Exception:
                continue
    # Sort by updated_at descending
    results.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return results


def _toggle_tf_content(file_path: Path, comment_out: bool) -> None:
    """Comment out or uncomment a Terraform resource file.

    When commented out, Terraform detects the resource has been removed from
    configuration and generates a destroy plan, updating the state in GCS upon apply.
    """
    lines = file_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if comment_out:
            if stripped and not stripped.startswith("#"):
                new_lines.append(f"# {line}")
            else:
                new_lines.append(line)
        else:
            if line.startswith("# "):
                new_lines.append(line[2:])
            elif line.startswith("#"):
                new_lines.append(line[1:])
            else:
                new_lines.append(line)

    file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _get_terraform_binary() -> str | None:
    """Locate the Terraform executable on PATH or standard installation locations."""
    which_path = shutil.which("terraform")
    if which_path and Path(which_path).is_file():
        return which_path
    for candidate in [
        "/usr/local/bin/terraform",
        "/usr/bin/terraform",
        Path.home() / ".local" / "bin" / "terraform",
        Path.home() / "bin" / "terraform",
    ]:
        p = Path(candidate)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _run_terraform(
    args: list[str],
    working_directory: Path,
    separate_stderr: bool = False,
) -> dict:
    """Run one fixed Terraform command directly without a shell."""
    terraform_path = _get_terraform_binary()
    if not terraform_path:
        return {
            "returncode": 127,
            "output": "Terraform CLI was not found. Run 'bash setup.sh' to install it automatically.",
            "stdout": "",
            "stderr": "Terraform CLI was not found.",
        }

    command = [terraform_path, *args]
    cmd_str = f"terraform {' '.join(args)}"
    print(f"\n[TaaS][CLI] Executing: {cmd_str}")
    print(f"[TaaS][CLI] In directory: {working_directory.resolve()}")
    try:
        if separate_stderr:
            result = subprocess.run(
                command,
                cwd=str(working_directory),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=PLAN_TIMEOUT_SECONDS,
                check=False,
            )
            print(f"[TaaS][CLI] Completed with return code: {result.returncode}")
            if result.returncode != 0:
                print(f"[TaaS][CLI Error] STDERR:\n{result.stderr}")
            return {
                "returncode": result.returncode,
                "output": (result.stdout if result.returncode == 0 else (result.stderr or result.stdout)) or "",
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }
        else:
            result = subprocess.run(
                command,
                cwd=str(working_directory),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=PLAN_TIMEOUT_SECONDS,
                check=False,
            )
            print(f"[TaaS][CLI] Completed with return code: {result.returncode}")
            if result.returncode != 0:
                print(f"[TaaS][CLI Error] Output:\n{result.stdout}")
            return {
                "returncode": result.returncode,
                "output": result.stdout or "",
                "stdout": result.stdout or "",
                "stderr": "",
            }
    except subprocess.TimeoutExpired:
        print(f"[TaaS][CLI Error] Command timed out after {PLAN_TIMEOUT_SECONDS}s")
        return {
            "returncode": 124,
            "output": f"Terraform command timed out after {PLAN_TIMEOUT_SECONDS} seconds.",
            "stdout": "",
            "stderr": "Timeout expired",
        }
    except OSError as exc:
        print(f"[TaaS][CLI Error] Could not start Terraform: {exc}")
        return {
            "returncode": 1,
            "output": f"Could not start Terraform: {exc}",
            "stdout": "",
            "stderr": str(exc),
        }


def _get_state_bucket(project_id: str) -> tuple[str | None, str | None]:
    """Inspect and require an existing, versioned GCS bucket for remote state."""
    bucket_name = os.getenv("TAAS_STATE_BUCKET", "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket_name):
        return None, (
            "TAAS_STATE_BUCKET environment variable is not set to a valid bucket name. "
            "Please configure TAAS_STATE_BUCKET with an existing versioned GCS bucket."
        )

    try:
        from google.cloud import storage

        bucket = storage.Client(project=project_id).get_bucket(bucket_name)
    except Exception as exc:
        return None, (
            f"Could not inspect GCS bucket '{bucket_name}': {exc}. "
            "Verify the bucket exists and current credentials have Storage permissions."
        )

    if not bucket.versioning_enabled:
        return None, (
            f"GCS bucket '{bucket_name}' does not have object versioning enabled. "
            "Object versioning is required for safe Terraform state tracking."
        )

    return bucket_name, None


def _validate_inputs(project_id: str, location: str, resource_name: str) -> list[str]:
    """Validate core identifiers."""
    errors = []
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id.strip()):
        errors.append(
            "Project ID must be 6-30 characters, start with a lowercase letter, "
            "and contain lowercase letters, numbers, or hyphens."
        )

    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?", location.strip()):
        errors.append("Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen.")

    if not re.fullmatch(r"[A-Za-z0-9_]{1,1024}", resource_name.strip()):
        errors.append("Resource name must contain only letters, numbers, or underscores.")

    return errors


# ==============================================================================
# Public Generic Tools
# ==============================================================================


def generate_resource_files(
    resource_type: str,
    project_id: str,
    location: str,
    resource_name: str,
    config: dict | None = None,
) -> dict:
    """Generate reviewable Terraform configuration files from approved starters.

    Args:
        resource_type: The type of resource (e.g. 'gcp.bigquery_dataset' or 'bigquery_dataset').
        project_id: Target Google Cloud project ID.
        location: Cloud location/region (e.g. 'US', 'us-central1').
        resource_name: Identifier for the resource (e.g. 'sales_data').
        config: Optional dictionary of additional settings.

    Returns:
        dict: Request metadata including request_id, artifact_directory, and generated files.
    """
    normalized_type = _normalize_resource_type(resource_type)
    if normalized_type not in SUPPORTED_RESOURCES:
        supported_list = ", ".join(SUPPORTED_RESOURCES.keys())
        return {
            "status": "UNSUPPORTED",
            "message": f"Resource type '{resource_type}' is not supported. Supported types: {supported_list}",
        }

    errors = _validate_inputs(project_id, location, resource_name)
    if errors:
        return {"status": "INVALID", "errors": errors}

    spec = SUPPORTED_RESOURCES[normalized_type]
    starter_dir = spec["starter_dir"]
    primary_tf_name = spec["primary_tf"]
    primary_tf = starter_dir / primary_tf_name

    starter_files = [
        COMMON_STARTER_DIR / "main.tf",
        COMMON_STARTER_DIR / "variables.tf",
        primary_tf,
    ]
    missing = [str(p) for p in starter_files if not p.is_file()]
    if missing:
        return {
            "status": "ERROR",
            "message": f"Missing approved Terraform starter file(s): {', '.join(missing)}",
        }

    request_id = str(uuid4())
    # Deterministic directory per resource so deactivation and recreation find it easily
    folder_name = f"{spec['provider']}_{spec['short_name']}_{project_id}_{resource_name}"
    output_dir = ARTIFACTS_DIR / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[TaaS] Generating artifacts for {normalized_type} '{resource_name}' in project '{project_id}'...")
    print(f"[TaaS] Artifact directory: {output_dir.resolve()}")

    # Copy common and resource-specific starters
    for starter in starter_files:
        shutil.copy2(starter, output_dir / starter.name)

    # Prepare resource_config map for terraform.tfvars
    res_config = dict(config or {})
    res_config[spec["name_param"]] = resource_name

    tfvars_content = (
        f"project_id = {json.dumps(project_id.strip())}\n"
        f"location   = {json.dumps(location.strip())}\n"
        f"resource_config = {json.dumps(res_config, indent=2)}\n"
    )
    (output_dir / "terraform.tfvars").write_text(tfvars_content, encoding="utf-8")

    # Write backend.tfvars so manual CLI operations work effortlessly (terraform init -backend-config=backend.tfvars)
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "").strip()
    prefix = f"taas/{project_id.strip()}/{normalized_type.replace('.', '/')}/{resource_name.strip()}"
    if state_bucket:
        backend_content = (
            f'bucket = "{state_bucket}"\n'
            f'prefix = "{prefix}"\n'
        )
        (output_dir / "backend.tfvars").write_text(backend_content, encoding="utf-8")

    record = {
        "request_id": request_id,
        "action": "CREATE",
        "resource_type": normalized_type,
        "resource_name": resource_name.strip(),
        "project_id": project_id.strip(),
        "location": location.strip(),
        "resource_config": res_config,
        "artifact_directory": str(output_dir.resolve()),
        "primary_tf_file": str((output_dir / primary_tf_name).resolve()),
        "expected_address": spec["expected_address"],
        "status": "ARTIFACTS_READY",
        "status_message": "Terraform artifacts generated and ready for planning.",
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save_record(record)

    return {
        "status": "SUCCESS",
        "request_id": request_id,
        "action": "CREATE",
        "resource_type": normalized_type,
        "resource_name": resource_name.strip(),
        "artifact_directory": str(output_dir.resolve()),
        "files": [
            str(output_dir / "main.tf"),
            str(output_dir / "variables.tf"),
            str(output_dir / primary_tf_name),
            str(output_dir / "terraform.tfvars"),
        ],
        "message": (
            f"Terraform files for {spec['description']} '{resource_name}' generated under "
            f"'{output_dir.name}'. Ready to run Terraform plan."
        ),
    }


def plan_resource(request_id: str) -> dict:
    """Format, initialize, validate, and plan a generated resource request.

    Inspects the plan AST to guarantee:
    - For CREATE / RECREATE actions: ONLY the requested resource creation is planned.
    - For DEACTIVATE actions: ONLY the requested resource deletion is planned.
    Any unexpected modification, addition, or destruction blocks the plan.

    Args:
        request_id: UUID of the request.

    Returns:
        dict: Plan summary and plan_sha256 digest awaiting user approval.
    """
    try:
        record = _load_record(request_id)
        working_directory = Path(record["artifact_directory"]).resolve()
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}

    bucket_name, bucket_error = _get_state_bucket(record["project_id"])
    if bucket_error:
        return {"status": "BLOCKED", "message": bucket_error}

    _set_status(record, "PLANNING", "Terraform plan is being generated.")

    # Unique prefix per resource keeps states isolated within the project state bucket
    prefix = f"taas/{record['project_id']}/{record['resource_type'].replace('.', '/')}/{record['resource_name']}"

    print(f"\n[TaaS] Starting planning for Request ID: {request_id}")
    print(f"[TaaS] Resource: {record.get('resource_type')} '{record.get('resource_name')}' (action: {record.get('action')})")
    print(f"[TaaS] Working directory: {working_directory}")
    print(f"[TaaS] State backend: bucket='{bucket_name}', prefix='{prefix}'")

    # 1. Format & Init
    init_steps = [
        ("fmt", ["fmt", "-recursive"]),
        (
            "init",
            [
                "init",
                "-input=false",
                "-reconfigure",
                f"-backend-config=bucket={bucket_name}",
                f"-backend-config=prefix={prefix}",
            ],
        ),
        ("validate", ["validate", "-no-color"]),
    ]

    for step_name, args in init_steps:
        result = _run_terraform(args, working_directory)
        if result["returncode"] != 0:
            _set_status(record, "PLAN_FAILED", f"Terraform {step_name} failed.")
            return {
                "status": "ERROR",
                "step": step_name,
                "message": result["output"][-12000:],
            }

    # 2. Plan directly inside working directory
    local_plan = working_directory / "terraform.tfplan"
    local_plan.unlink(missing_ok=True)
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
            "-out=terraform.tfplan",
        ],
        working_directory,
    )
    if result["returncode"] != 0:
        _set_status(record, "PLAN_FAILED", "Terraform plan failed.")
        return {"status": "ERROR", "step": "plan", "message": result["output"][-16000:]}

    # Backup the plan file to the private request directory
    if local_plan.is_file():
        shutil.copy2(local_plan, saved_plan)

    readable_plan = _run_terraform(["show", "-no-color", "terraform.tfplan"], working_directory)
    json_plan = _run_terraform(
        ["show", "-json", "terraform.tfplan"],
        working_directory,
        separate_stderr=True,
    )

    raw_output = (json_plan.get("stdout") or json_plan.get("output") or "").strip()
    raw_err = json_plan.get("stderr", "")
    print(f"[TaaS][CLI] Plan JSON output length: {len(raw_output)} chars, stderr: {len(raw_err)} chars")

    if json_plan["returncode"] != 0:
        _set_status(record, "PLAN_FAILED", "Could not inspect Terraform plan JSON.")
        return {"status": "ERROR", "message": json_plan["output"][-12000:]}

    # Find JSON boundaries in case any warning lines were printed before '{'
    start_idx = raw_output.find("{")
    end_idx = raw_output.rfind("}")
    if start_idx != -1 and end_idx != -1:
        clean_json = raw_output[start_idx : end_idx + 1]
    else:
        clean_json = raw_output

    try:
        plan_data = json.loads(clean_json)
    except json.JSONDecodeError as err:
        preview = raw_output[:1000]
        print(f"[TaaS Error] Failed to parse plan JSON: {err}")
        print(f"[TaaS Error] Raw output:\n{raw_output}")
        _set_status(record, "PLAN_FAILED", f"Invalid plan JSON: {err}. Preview: {preview}")
        return {
            "status": "ERROR",
            "message": f"Failed to parse Terraform plan JSON: {err}.\nRaw Output:\n{preview}\nSTDERR:\n{raw_err}",
        }

    # 3. Inspect Plan AST for Safety
    action = record.get("action", "CREATE")
    expected_actions = ["delete"] if action == "DEACTIVATE" else ["create"]
    expected_address = record.get("expected_address", "")

    unexpected_changes = []
    for change in plan_data.get("resource_changes", []):
        address = change.get("address", "unknown")
        actions = change.get("change", {}).get("actions", [])
        if actions == ["no-op"]:
            continue
        if address != expected_address or actions != expected_actions:
            unexpected_changes.append({"address": address, "actions": actions})

    if unexpected_changes:
        _set_status(record, "BLOCKED_PLAN", "Plan contains unauthorized resource changes.")
        return {
            "status": "BLOCKED",
            "message": f"Plan contains unexpected actions {unexpected_changes}. Expected {expected_actions} on {expected_address}.",
            "unexpected_changes": unexpected_changes,
            "plan_summary": readable_plan["output"][:30000],
        }

    # 4. Hash plan and save awaiting user confirmation
    digest = hashlib.sha256(saved_plan.read_bytes()).hexdigest()
    record["plan_sha256"] = digest
    record["plan_file"] = str(saved_plan.resolve())
    record["plan_summary"] = readable_plan["output"]
    _set_status(
        record,
        "AWAITING_APPROVAL",
        f"Plan for action '{action}' is ready. Review and approve before apply.",
    )

    action_label = "destruction/deactivation" if action == "DEACTIVATE" else "creation"
    return {
        "status": "AWAITING_APPROVAL",
        "request_id": request_id,
        "action": action,
        "plan_sha256": digest,
        "plan_summary": readable_plan["output"][:30000],
        "message": (
            f"Terraform plan for {action_label} is ready. "
            "Please review the plan summary and explicitly confirm the apply tool call to proceed."
        ),
    }


def apply_resource(request_id: str, plan_sha256: str) -> dict:
    """Apply the approved Terraform plan.

    Gated by ADK tool confirmation (`require_confirmation=True`).
    Verifies that the plan file has not changed since inspection.

    Args:
        request_id: UUID of the request.
        plan_sha256: SHA-256 digest of the plan returned during planning.

    Returns:
        dict: Apply summary and status.
    """
    try:
        record = _load_record(request_id)
        working_directory = Path(record["artifact_directory"]).resolve()
        saved_plan = _request_record_path(request_id).parent / "terraform.tfplan"
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}

    if record.get("status") != "AWAITING_APPROVAL":
        return {
            "status": "BLOCKED",
            "message": f"Request status is '{record.get('status')}'; a plan must be awaiting approval.",
        }

    if plan_sha256 != record.get("plan_sha256"):
        return {
            "status": "BLOCKED",
            "message": "The provided plan digest does not match the plan presented for approval.",
        }

    if not saved_plan.is_file():
        return {"status": "ERROR", "message": "Saved plan file is missing."}

    actual_digest = hashlib.sha256(saved_plan.read_bytes()).hexdigest()
    if actual_digest != plan_sha256:
        return {
            "status": "BLOCKED",
            "message": "The plan file changed after review. Please generate and review a new plan.",
        }

    local_plan = working_directory / "terraform.tfplan"
    plan_target = "terraform.tfplan" if local_plan.is_file() else str(saved_plan)

    print(f"\n[TaaS] Applying approved Terraform plan for Request ID: {request_id}")
    print(f"[TaaS] Target plan file: {plan_target} in {working_directory.resolve()}")

    _set_status(record, "APPLYING", "Applying approved Terraform plan.")

    result = _run_terraform(
        [
            "apply",
            "-input=false",
            "-no-color",
            "-lock-timeout=5m",
            plan_target,
        ],
        working_directory,
    )

    print(f"[TaaS] Apply returned code: {result['returncode']}")
    if result["returncode"] != 0:
        print(f"[TaaS Error] Apply failed:\n{result['output']}")
        _set_status(record, "APPLY_FAILED", "Terraform apply failed.")
        return {"status": "ERROR", "step": "apply", "message": result["output"][-16000:]}

    print(f"[TaaS] Apply succeeded:\n{result['output'][-500:]}")
    record["apply_summary"] = result["output"]
    action = record.get("action", "CREATE")

    if action == "DEACTIVATE":
        _set_status(
            record,
            "DEACTIVATED",
            "Resource has been deactivated and deleted from cloud. Verification is next.",
        )
    else:
        _set_status(
            record,
            "APPLIED",
            "Resource applied successfully. Verification is next.",
        )

    return {
        "status": record["status"],
        "request_id": request_id,
        "action": action,
        "message": (
            f"Terraform apply completed for action '{action}'. "
            "Remote state in GCS has been updated. Next, run verify_resource."
        ),
        "apply_summary": result["output"][-12000:],
    }


def plan_deactivate_resource(
    project_id: str,
    resource_name: str,
    resource_type: str = "gcp.bigquery_dataset",
) -> dict:
    """Comment out a resource's Terraform code and generate a destroy plan.

    The resource code remains preserved in the artifacts directory with comments (#)
    so it can be recreated anytime using plan_recreate_resource.

    Args:
        project_id: The Google Cloud project ID.
        resource_name: Identifier for the resource (e.g. 'sales_data').
        resource_type: Resource type (default: 'gcp.bigquery_dataset').

    Returns:
        dict: Destruction plan summary awaiting approval.
    """
    normalized_type = _normalize_resource_type(resource_type)
    matching = _find_records(project_id=project_id, resource_name=resource_name, resource_type=normalized_type)
    if not matching:
        return {
            "status": "NOT_FOUND",
            "message": f"No existing deployment found for {normalized_type} '{resource_name}' in project '{project_id}'.",
        }

    active_record = matching[0]
    tf_file = Path(active_record["primary_tf_file"])
    if not tf_file.is_file():
        return {
            "status": "ERROR",
            "message": f"Primary Terraform file '{tf_file}' not found.",
        }

    # 1. Comment out the resource block in the .tf file
    _toggle_tf_content(tf_file, comment_out=True)

    # 2. Create a new deactivation request record
    deact_id = str(uuid4())
    new_record = dict(active_record)
    new_record["request_id"] = deact_id
    new_record["action"] = "DEACTIVATE"
    new_record["status"] = "ARTIFACTS_READY"
    new_record["status_message"] = "Resource configuration commented out. Ready to plan deactivation."
    new_record["created_at"] = _now()
    new_record["updated_at"] = _now()
    _save_record(new_record)

    # 3. Run plan_resource for the deactivation action
    return plan_resource(deact_id)


def plan_recreate_resource(
    project_id: str,
    resource_name: str,
    resource_type: str = "gcp.bigquery_dataset",
) -> dict:
    """Uncomment a previously deactivated resource and generate a create plan.

    Args:
        project_id: The Google Cloud project ID.
        resource_name: Identifier for the resource (e.g. 'sales_data').
        resource_type: Resource type (default: 'gcp.bigquery_dataset').

    Returns:
        dict: Creation plan summary awaiting approval.
    """
    normalized_type = _normalize_resource_type(resource_type)
    matching = _find_records(project_id=project_id, resource_name=resource_name, resource_type=normalized_type)
    if not matching:
        return {
            "status": "NOT_FOUND",
            "message": f"No existing record found for {normalized_type} '{resource_name}' in project '{project_id}'.",
        }

    active_record = matching[0]
    tf_file = Path(active_record["primary_tf_file"])
    if not tf_file.is_file():
        return {"status": "ERROR", "message": f"Primary Terraform file '{tf_file}' not found."}

    # 1. Uncomment the resource block in the .tf file
    _toggle_tf_content(tf_file, comment_out=False)

    # 2. Create a recreation request record
    recreate_id = str(uuid4())
    new_record = dict(active_record)
    new_record["request_id"] = recreate_id
    new_record["action"] = "RECREATE"
    new_record["status"] = "ARTIFACTS_READY"
    new_record["status_message"] = "Resource configuration restored. Ready to plan recreation."
    new_record["created_at"] = _now()
    new_record["updated_at"] = _now()
    _save_record(new_record)

    # 3. Run plan_resource for the recreation action
    return plan_resource(recreate_id)


# ==============================================================================
# Verification Handlers
# ==============================================================================


async def _verify_bigquery(record: dict) -> dict:
    """Verify BigQuery dataset existence or deletion."""
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=record["project_id"])
    dataset_name = f"{record['project_id']}.{record['resource_name']}"
    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"

    print(f"\n[TaaS] Verifying {action_label} for dataset '{dataset_name}' via BigQuery API...")

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] BigQuery API verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        try:
            dataset = await asyncio.to_thread(client.get_dataset, dataset_name)
            print(f"[TaaS] Found dataset in location: {dataset.location}")
            if is_deactivation:
                # Still exists, wait for deletion
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", "Dataset still exists in BigQuery.")
                return {
                    "status": "VERIFYING",
                    "message": "Dataset is still visible in BigQuery; deletion is still processing.",
                }

            # For creation / recreation: verify location matches
            if dataset.location.casefold() != record["location"].casefold():
                _set_status(record, "VERIFICATION_FAILED", "Location mismatch.")
                return {
                    "status": "ERROR",
                    "message": f"Dataset location '{dataset.location}' does not match requested '{record['location']}'.",
                }

            _set_status(record, "READY", "Dataset verified and ready in BigQuery.")
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "resource_name": record["resource_name"],
                "location": dataset.location,
                "message": f"BigQuery dataset '{record['resource_name']}' is confirmed READY in project '{record['project_id']}'.",
            }
        except NotFound:
            if is_deactivation:
                # Successfully deleted!
                _set_status(record, "DELETED", "Dataset confirmed deleted from BigQuery. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "resource_name": record["resource_name"],
                    "message": (
                        f"BigQuery dataset '{record['resource_name']}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }

            # Still provisioning
            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)

    if is_deactivation:
        return {
            "status": "VERIFYING",
            "message": "Dataset deletion not yet reflected in BigQuery. Please retry verification shortly.",
        }
    return {
        "status": "VERIFYING",
        "message": "Dataset is not yet visible in BigQuery. Please retry verification shortly.",
    }


VERIFIERS = {
    "gcp.bigquery_dataset": _verify_bigquery,
}


async def verify_resource(request_id: str) -> dict:
    """Asynchronously verify that a cloud resource exists (if created) or is deleted (if deactivated).

    Args:
        request_id: UUID of the request.

    Returns:
        dict: Verification result.
    """
    try:
        record = _load_record(request_id)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}

    verifier = VERIFIERS.get(record["resource_type"])
    if not verifier:
        return {
            "status": "READY",
            "message": f"No custom verifier configured for {record['resource_type']}. Marked READY.",
        }

    return await verifier(record)


def get_request_status(request_id: str) -> dict:
    """Get the current progress and status of a TaaS request."""
    try:
        record = _load_record(request_id)
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}

    return {
        "status": record.get("status", "UNKNOWN"),
        "request_id": record["request_id"],
        "action": record.get("action", "CREATE"),
        "resource_type": record.get("resource_type"),
        "resource_name": record.get("resource_name"),
        "project_id": record.get("project_id"),
        "location": record.get("location"),
        "status_message": record.get("status_message"),
        "updated_at": record.get("updated_at"),
    }


def list_taas_resources(project_id: str | None = None) -> dict:
    """List all managed cloud resources and their latest statuses."""
    records = _find_records(project_id=project_id)
    # Deduplicate by (project_id, resource_type, resource_name) taking most recent
    seen = {}
    for r in records:
        key = (r.get("project_id"), r.get("resource_type"), r.get("resource_name"))
        if key not in seen:
            seen[key] = {
                "project_id": r.get("project_id"),
                "resource_type": r.get("resource_type"),
                "resource_name": r.get("resource_name"),
                "location": r.get("location"),
                "status": r.get("status"),
                "action": r.get("action"),
                "artifact_directory": r.get("artifact_directory"),
                "last_updated": r.get("updated_at"),
            }

    return {
        "status": "SUCCESS",
        "count": len(seen),
        "resources": list(seen.values()),
    }
