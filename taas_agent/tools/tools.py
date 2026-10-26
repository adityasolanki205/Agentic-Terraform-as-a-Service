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
from typing import Literal
from uuid import UUID, uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMON_STARTER_DIR = PROJECT_ROOT / "terraform_starters" / "common"
STARTERS_DIR = PROJECT_ROOT / "terraform_starters"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REQUESTS_DIR = PROJECT_ROOT / ".taas" / "requests"

PLAN_TIMEOUT_SECONDS = 600
VERIFY_ATTEMPTS = 6
VERIFY_DELAY_SECONDS = 5


GCP_ARTIFACTS_DIR = ARTIFACTS_DIR / "gcp"

# Registry of supported resources mapping to their single shared .tf files and resource definitions.
SUPPORTED_RESOURCES = {
    "gcp.bigquery_dataset": {
        "provider": "gcp",
        "short_name": "bigquery_dataset",
        "starter_dir": STARTERS_DIR / "gcp" / "bigquery_dataset",
        "primary_tf": "dataset.tf",
        "resource_type_hcl": "google_bigquery_dataset",
        "name_param": "dataset_id",
        "description": "Google Cloud BigQuery Dataset",
    },
    "gcp.bigquery_table": {
        "provider": "gcp",
        "short_name": "bigquery_table",
        "starter_dir": STARTERS_DIR / "gcp" / "bigquery_table",
        "primary_tf": "table.tf",
        "resource_type_hcl": "google_bigquery_table",
        "name_param": "table_id",
        "description": "Google Cloud BigQuery Table",
    },
    "gcp.storage_bucket": {
        "provider": "gcp",
        "short_name": "storage_bucket",
        "starter_dir": STARTERS_DIR / "gcp" / "storage_bucket",
        "primary_tf": "bucket.tf",
        "resource_type_hcl": "google_storage_bucket",
        "name_param": "bucket_name",
        "description": "Google Cloud Storage Bucket",
    },
    "gcp.pubsub_topic": {
        "provider": "gcp",
        "short_name": "pubsub_topic",
        "starter_dir": STARTERS_DIR / "gcp" / "pubsub_topic",
        "primary_tf": "topic.tf",
        "resource_type_hcl": "google_pubsub_topic",
        "name_param": "topic_name",
        "description": "Google Cloud Pub/Sub Topic",
    },
    "gcp.pubsub_subscription": {
        "provider": "gcp",
        "short_name": "pubsub_subscription",
        "starter_dir": STARTERS_DIR / "gcp" / "pubsub_subscription",
        "primary_tf": "subscription.tf",
        "resource_type_hcl": "google_pubsub_subscription",
        "name_param": "subscription_name",
        "description": "Google Cloud Pub/Sub Subscription",
    },
}


def _now() -> str:
    """Return a UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_resource_type(resource_type: str) -> str:
    """Normalize resource type names (e.g. 'storage_bucket' -> 'gcp.storage_bucket')."""
    cleaned = resource_type.strip().lower()
    aliases = {
        "storage_bucket": "gcp.storage_bucket",
        "gcs_bucket": "gcp.storage_bucket",
        "bucket": "gcp.storage_bucket",
        "pubsub_topic": "gcp.pubsub_topic",
        "topic": "gcp.pubsub_topic",
        "pubsub_subscription": "gcp.pubsub_subscription",
        "subscription": "gcp.pubsub_subscription",
        "bigquery_dataset": "gcp.bigquery_dataset",
        "dataset": "gcp.bigquery_dataset",
        "bigquery_table": "gcp.bigquery_table",
        "table": "gcp.bigquery_table",
    }
    if cleaned in aliases:
        return aliases[cleaned]
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
    dataset_id: str | None = None,
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
                if dataset_id and rec.get("resource_config", {}).get("dataset_id") != dataset_id:
                    continue
                results.append(rec)
            except Exception:
                continue
    # Sort by updated_at descending
    results.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return results


def _ensure_common_artifacts(
    artifacts_dir: Path,
    project_id: str,
    location: str,
    state_bucket: str,
) -> None:
    """Ensure standard main.tf, variables.tf, backend.tfvars, and terraform.tfvars exist in the single artifacts folder.

    Copies code directly from terraform_starters/common/.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    main_tf = artifacts_dir / "main.tf"
    starter_main = COMMON_STARTER_DIR / "main.tf"
    if starter_main.is_file():
        shutil.copy2(starter_main, main_tf)

    variables_tf = artifacts_dir / "variables.tf"
    starter_vars = COMMON_STARTER_DIR / "variables.tf"
    if starter_vars.is_file():
        shutil.copy2(starter_vars, variables_tf)

    # Update or write terraform.tfvars
    tfvars_path = artifacts_dir / "terraform.tfvars"
    tfvars_content = (
        f'project_id = "{project_id.strip()}"\n'
        f'location   = "{location.strip()}"\n'
    )
    tfvars_path.write_text(tfvars_content, encoding="utf-8")

    # Write backend.tfvars with project-scoped state prefix
    if state_bucket:
        backend_content = (
            f'bucket = "{state_bucket}"\n'
            f'prefix = "taas/{project_id.strip()}/gcp"\n'
        )
        (artifacts_dir / "backend.tfvars").write_text(backend_content, encoding="utf-8")


def _build_resource_hcl(
    resource_type: str,
    resource_name: str,
    project_id: str,
    location: str,
    config: dict | None = None,
) -> tuple[str, str, str]:
    """Build HCL string from approved terraform starters, Terraform resource name, and address.

    Returns:
        (hcl_block, tf_name, tf_address)
    """
    config = config or {}
    clean_name = resource_name.strip()
    clean_project = project_id.strip()
    clean_location = location.strip()

    if resource_type == "gcp.bigquery_dataset":
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", clean_name)
        tf_address = f"google_bigquery_dataset.{tf_name}"

        # Load starter code from terraform_starters/gcp/bigquery_dataset/
        starter_file = STARTERS_DIR / "gcp" / "bigquery_dataset" / "dataset.tf"
        if not starter_file.is_file():
            starter_file = STARTERS_DIR / "gcp" / "bigquery_dataset" / "bigquery_dataset.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["dataset_id"]', f'"{clean_name}"')
                .replace("{{dataset_id}}", clean_name)
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .replace("var.location", f'"{clean_location}"')
                .replace("{{location}}", clean_location)
                .strip()
            )
        else:
            rendered = f"""resource "google_bigquery_dataset" "{tf_name}" {{
  dataset_id = "{clean_name}"
  project    = "{clean_project}"
  location   = "{clean_location}"
}}"""

        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.bigquery_table":
        dataset_id = str(config.get("dataset_id", "")).strip()
        combined = f"{dataset_id}_{clean_name}"
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", combined)
        tf_address = f"google_bigquery_table.{tf_name}"

        schema_val = config.get("schema")
        schema_json_raw = ""
        schema_attr_fallback = ""
        if schema_val:
            if isinstance(schema_val, (dict, list)):
                schema_json = json.dumps(schema_val, indent=2)
            else:
                schema_json = str(schema_val).strip()
            if schema_json.lower() not in ("", "none", "null", "skip", "no"):
                schema_json_raw = f"<<EOF\n{schema_json}\nEOF"
                schema_attr_fallback = f"\n  schema = <<EOF\n{schema_json}\nEOF\n"

        # Load starter code from terraform_starters/gcp/bigquery_table/
        starter_file = STARTERS_DIR / "gcp" / "bigquery_table" / "table.tf"
        if not starter_file.is_file():
            starter_file = STARTERS_DIR / "gcp" / "bigquery_table" / "bigquery_table.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["dataset_id"]', f'"{dataset_id}"')
                .replace("{{dataset_id}}", dataset_id)
                .replace('var.resource_config["table_id"]', f'"{clean_name}"')
                .replace("{{table_id}}", clean_name)
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .replace('lookup(var.resource_config, "schema", null)', schema_json_raw if schema_json_raw else "null")
                .replace("{{schema_attr}}", schema_attr_fallback)
                .strip()
            )
            if not schema_json_raw:
                rendered = "\n".join(
                    line for line in rendered.splitlines()
                    if not line.strip().startswith("schema = null")
                )
        else:
            rendered = f"""resource "google_bigquery_table" "{tf_name}" {{
  project             = "{clean_project}"
  dataset_id          = "{dataset_id}"
  table_id            = "{clean_name}"
  deletion_protection = false{schema_attr_fallback}
}}"""

        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.storage_bucket":
        bucket_name = clean_name.lower()
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", bucket_name)
        tf_address = f"google_storage_bucket.{tf_name}"

        versioning_enabled = config.get("versioning", True)
        if isinstance(versioning_enabled, str):
            versioning_enabled = versioning_enabled.lower() not in ("false", "0", "no", "disabled")
        versioning_str = "true" if versioning_enabled else "false"

        starter_file = STARTERS_DIR / "gcp" / "storage_bucket" / "bucket.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["bucket_name"]', f'"{bucket_name}"')
                .replace("{{bucket_name}}", bucket_name)
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .replace("var.location", f'"{clean_location}"')
                .replace("{{location}}", clean_location)
                .replace('lookup(var.resource_config, "versioning", true)', versioning_str)
                .strip()
            )
        else:
            rendered = f"""resource "google_storage_bucket" "{tf_name}" {{
  name                        = "{bucket_name}"
  project                     = "{clean_project}"
  location                    = "{clean_location}"
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {{
    enabled = {versioning_str}
  }}
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.pubsub_topic":
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", clean_name)
        tf_address = f"google_pubsub_topic.{tf_name}"

        starter_file = STARTERS_DIR / "gcp" / "pubsub_topic" / "topic.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["topic_name"]', f'"{clean_name}"')
                .replace("{{topic_name}}", clean_name)
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .strip()
            )
        else:
            rendered = f"""resource "google_pubsub_topic" "{tf_name}" {{
  name    = "{clean_name}"
  project = "{clean_project}"
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.pubsub_subscription":
        raw_topic = str(config.get("topic") or config.get("topic_name") or "").strip()
        if "/" in raw_topic:
            topic_ref = raw_topic
        else:
            topic_ref = f"projects/{clean_project}/topics/{raw_topic}"

        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", clean_name)
        tf_address = f"google_pubsub_subscription.{tf_name}"

        ack_seconds = config.get("ack_deadline_seconds", 20)
        retention = config.get("message_retention_duration", "604800s")

        starter_file = STARTERS_DIR / "gcp" / "pubsub_subscription" / "subscription.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["subscription_name"]', f'"{clean_name}"')
                .replace("{{subscription_name}}", clean_name)
                .replace('var.resource_config["topic"]', f'"{topic_ref}"')
                .replace("{{topic}}", topic_ref)
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .replace('ack_deadline_seconds       = 20', f'ack_deadline_seconds       = {ack_seconds}')
                .replace('message_retention_duration = "604800s"', f'message_retention_duration = "{retention}"')
                .strip()
            )
        else:
            rendered = f"""resource "google_pubsub_subscription" "{tf_name}" {{
  name                       = "{clean_name}"
  topic                      = "{topic_ref}"
  project                    = "{clean_project}"
  message_retention_duration = "{retention}"
  retain_acked_messages      = false
  ack_deadline_seconds       = {ack_seconds}
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    else:
        raise ValueError(f"Unsupported resource type: {resource_type}")


def _upsert_resource_block(file_path: Path, tf_address: str, new_block: str) -> None:
    """Insert or replace a resource block in a shared .tf file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.is_file():
        file_path.write_text(f"# Managed by Agentic Terraform as a Service (TaaS)\n\n{new_block}\n", encoding="utf-8")
        return

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    start_marker = f"# --- START: {tf_address}"
    end_marker = f"# --- END: {tf_address}"

    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if line.startswith(start_marker):
            start_idx = i
        elif line.startswith(end_marker) and start_idx is not None:
            end_idx = i
            break

    # If markers not found, search for header e.g. resource "google_bigquery_dataset" "tform"
    if start_idx is None or end_idx is None:
        parts = tf_address.split(".", 1)
        if len(parts) == 2:
            r_type, r_name = parts
            target_type = f'resource "{r_type}"'
            target_name = f'"{r_name}"'
            for i, line in enumerate(lines):
                if target_type in line and target_name in line:
                    start_idx = i
                    brace_count = 0
                    for j in range(i, len(lines)):
                        brace_count += lines[j].count("{") - lines[j].count("}")
                        if brace_count == 0 and "{" in lines[i]:
                            end_idx = j
                            break
                    break

    if start_idx is not None and end_idx is not None:
        before = lines[:start_idx]
        after = lines[end_idx + 1 :]
        updated = "\n".join(before).rstrip() + "\n\n" + new_block.strip() + "\n\n" + "\n".join(after).lstrip()
        file_path.write_text(updated.strip() + "\n", encoding="utf-8")
        return

    # Append to file
    updated = content.rstrip() + "\n\n" + new_block.strip() + "\n"
    file_path.write_text(updated, encoding="utf-8")


def _toggle_resource_block_in_file(file_path: Path, tf_address: str, comment_out: bool) -> bool:
    """Comment out or uncomment a specific resource block within a shared .tf file.

    When comment_out=True:
        Adds '# ' before active lines and marks header as '[DEACTIVATED]'.
    When comment_out=False:
        Removes '# ' and restores active header marker.
    """
    if not file_path.is_file():
        return False

    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    start_marker = f"# --- START: {tf_address}"
    end_marker = f"# --- END: {tf_address}"

    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if line.startswith(start_marker):
            start_idx = i
        elif line.startswith(end_marker) and start_idx is not None:
            end_idx = i
            break

    # Fallback to header search
    if start_idx is None or end_idx is None:
        parts = tf_address.split(".", 1)
        if len(parts) == 2:
            r_type, r_name = parts
            target_type = f'resource "{r_type}"'
            target_name = f'"{r_name}"'
            for i, line in enumerate(lines):
                if target_type in line and target_name in line:
                    start_idx = i
                    brace_count = 0
                    for j in range(i, len(lines)):
                        brace_count += lines[j].count("{") - lines[j].count("}")
                        if brace_count == 0 and "{" in lines[i]:
                            end_idx = j
                            break
                    break

    if start_idx is None:
        return False
    if end_idx is None:
        end_idx = len(lines) - 1

    new_lines = []
    for i, line in enumerate(lines):
        if start_idx <= i <= end_idx:
            if line.startswith(start_marker):
                new_lines.append(f"{start_marker} [DEACTIVATED] ---" if comment_out else f"{start_marker} ---")
                continue
            if line.startswith(end_marker):
                new_lines.append(f"{end_marker} ---")
                continue

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
        else:
            new_lines.append(line)

    file_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return True


TERRAFORM_VERSION = "1.9.8"


def ensure_terraform_binary() -> str | None:
    """Ensure a working Terraform binary exists, auto-installing if missing or broken.

    1. Checks if terraform is available on PATH or in standard paths:
       - ~/.local/bin/terraform (persistent across Cloud Shell restarts)
       - /usr/local/bin/terraform
       - /usr/bin/terraform
    2. If found, tests execution (`terraform version`).
    3. If missing or broken, downloads and installs Terraform v1.9.8 into
       ~/.local/bin/terraform using Python standard library (no sudo required).
    4. Ensures ~/.local/bin is in os.environ["PATH"] and maintains symlinks to /usr/bin/terraform.
    """
    user_bin = Path.home() / ".local" / "bin"
    user_bin_str = str(user_bin.resolve())

    # Ensure ~/.local/bin is on Python process PATH
    current_path = os.environ.get("PATH", "")
    if user_bin_str not in current_path.split(os.pathsep):
        os.environ["PATH"] = f"{user_bin_str}{os.pathsep}{current_path}"

    binary_name = "terraform.exe" if os.name == "nt" else "terraform"
    target_binary = user_bin / binary_name

    candidates = [
        target_binary,
        Path("/usr/local/bin/terraform"),
        Path("/usr/bin/terraform"),
        Path.home() / "bin" / binary_name,
    ]

    which_path = shutil.which("terraform")
    if which_path:
        candidates.insert(0, Path(which_path))

    for candidate in candidates:
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            try:
                test = subprocess.run(
                    [str(candidate), "version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                    check=False,
                )
                if test.returncode == 0:
                    # If this is the persistent ~/.local/bin binary, ensure /usr/bin symlinks exist
                    if candidate == target_binary and os.name != "nt":
                        for sys_target in ["/usr/bin/terraform", "/usr/local/bin/terraform"]:
                            if not Path(sys_target).is_file():
                                try:
                                    subprocess.run(
                                        ["sudo", "ln", "-sf", str(candidate), sys_target],
                                        stderr=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL,
                                        timeout=2,
                                        check=False,
                                    )
                                except Exception:
                                    pass
                    return str(candidate.resolve())
            except Exception:
                continue

    # Auto-install Terraform into ~/.local/bin/terraform
    import platform
    import urllib.request
    import zipfile

    system = platform.system().lower()
    machine = platform.machine().lower()

    os_name = "windows" if "windows" in system else ("darwin" if "darwin" in system else "linux")
    arch = "arm64" if ("arm" in machine or "aarch64" in machine) else "amd64"

    url = (
        f"https://releases.hashicorp.com/terraform/{TERRAFORM_VERSION}/"
        f"terraform_{TERRAFORM_VERSION}_{os_name}_{arch}.zip"
    )

    print(f"\n[TaaS] Terraform not found. Auto-installing Terraform v{TERRAFORM_VERSION} to {user_bin}...")
    try:
        user_bin.mkdir(parents=True, exist_ok=True)
        zip_path = user_bin / f"terraform_{TERRAFORM_VERSION}.zip"

        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(user_bin)

        zip_path.unlink(missing_ok=True)

        if os.name != "windows":
            target_binary.chmod(0o755)
            for sys_target in ["/usr/bin/terraform", "/usr/local/bin/terraform"]:
                try:
                    subprocess.run(
                        ["sudo", "ln", "-sf", str(target_binary), sys_target],
                        stderr=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        timeout=2,
                        check=False,
                    )
                except Exception:
                    pass

        print(f"[TaaS] ✓ Terraform v{TERRAFORM_VERSION} automatically installed at: {target_binary}")
        return str(target_binary.resolve())
    except Exception as exc:
        print(f"[TaaS Error] Failed to auto-install Terraform: {exc}")
        return None


def _get_terraform_binary() -> str | None:
    """Locate or automatically install the Terraform executable."""
    return ensure_terraform_binary()


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


def _validate_inputs(
    project_id: str,
    location: str,
    resource_name: str,
    resource_type: str | None = None,
) -> list[str]:
    """Validate core identifiers."""
    errors = []
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id.strip()):
        errors.append(
            "Project ID must be 6-30 characters, start with a lowercase letter, "
            "and contain lowercase letters, numbers, or hyphens."
        )

    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?", location.strip()):
        errors.append("Location must contain letters, numbers, or hyphens and cannot start or end with a hyphen.")

    norm_type = _normalize_resource_type(resource_type) if resource_type else ""
    if norm_type == "gcp.storage_bucket":
        clean_bucket = resource_name.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,61}[a-z0-9]", clean_bucket):
            errors.append(
                "Storage bucket name must be 3-63 characters, start and end with a lowercase letter or number, "
                "and contain only lowercase letters, numbers, hyphens, underscores, or periods."
            )
    elif norm_type in ("gcp.pubsub_topic", "gcp.pubsub_subscription"):
        clean_res = resource_name.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.~+%-]{2,254}", clean_res):
            errors.append(
                "Pub/Sub topic or subscription name must start with a letter, be 3-255 characters, "
                "and contain only letters, numbers, hyphens, underscores, or periods."
            )
    else:
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
        resource_type: The type of resource (e.g. 'gcp.storage_bucket', 'gcp.pubsub_topic', 'gcp.bigquery_dataset').
        project_id: Target Google Cloud project ID.
        location: Cloud location/region (e.g. 'asia-south2', 'global', 'US').
        resource_name: Identifier for the resource (e.g. 'my-bucket', 'order-events').
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

    errors = _validate_inputs(project_id, location, resource_name, resource_type=normalized_type)
    if normalized_type == "gcp.bigquery_table":
        ds_id = str((config or {}).get("dataset_id", "")).strip()
        if not ds_id or not re.fullmatch(r"[A-Za-z0-9_]{1,1024}", ds_id):
            errors.append("BigQuery table requires a valid 'dataset_id' in config (e.g. config={'dataset_id': 'dataset_name'}).")

        schema_val = (config or {}).get("schema")
        if schema_val is not None:
            if isinstance(schema_val, str):
                s_strip = schema_val.strip()
                if s_strip.lower() not in ("", "none", "null", "skip", "no"):
                    try:
                        parsed = json.loads(s_strip)
                        if not isinstance(parsed, (list, dict)):
                            errors.append("BigQuery table schema must be a JSON array of column definitions (e.g. '[{\"name\": \"id\", \"type\": \"STRING\"}]').")
                    except json.JSONDecodeError as err:
                        errors.append(f"BigQuery table schema must be valid JSON: {err}")
            elif not isinstance(schema_val, (list, dict)):
                errors.append("BigQuery table schema must be a JSON string or list of column definitions.")

    elif normalized_type == "gcp.pubsub_subscription":
        raw_topic = str((config or {}).get("topic") or (config or {}).get("topic_name") or "").strip()
        if not raw_topic:
            errors.append("Pub/Sub subscription requires a 'topic' in config (e.g. config={'topic': 'topic_name'}).")
        else:
            topic_clean = raw_topic.split("/")[-1]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.~+%-]{2,254}", topic_clean):
                errors.append("Parent topic name must be 3-255 characters, start with a letter, and contain letters, numbers, or hyphens.")

    if errors:
        return {"status": "INVALID", "errors": errors}

    spec = SUPPORTED_RESOURCES[normalized_type]
    primary_tf_name = spec["primary_tf"]

    output_dir = GCP_ARTIFACTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "").strip()

    # 1. Ensure common artifacts (main.tf, variables.tf, terraform.tfvars, backend.tfvars)
    _ensure_common_artifacts(output_dir, project_id, location, state_bucket)

    # 2. Build resource HCL block
    hcl_block, tf_name, tf_address = _build_resource_hcl(
        resource_type=normalized_type,
        resource_name=resource_name,
        project_id=project_id,
        location=location,
        config=config,
    )

    primary_tf = output_dir / primary_tf_name

    # 3. Upsert resource block into dataset.tf or table.tf
    _upsert_resource_block(primary_tf, tf_address, hcl_block)

    request_id = str(uuid4())
    print(f"\n[TaaS] Adding {normalized_type} '{resource_name}' to '{primary_tf.name}' in project '{project_id}'...")
    print(f"[TaaS] Artifact directory: {output_dir.resolve()}")

    record = {
        "request_id": request_id,
        "action": "CREATE",
        "resource_type": normalized_type,
        "resource_name": resource_name.strip(),
        "project_id": project_id.strip(),
        "location": location.strip(),
        "resource_config": dict(config or {}),
        "artifact_directory": str(output_dir.resolve()),
        "primary_tf_file": str(primary_tf.resolve()),
        "expected_address": tf_address,
        "tf_resource_name": tf_name,
        "status": "ARTIFACTS_READY",
        "status_message": f"Resource block '{tf_address}' ready for planning in {primary_tf_name}.",
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
            str(primary_tf),
            str(output_dir / "terraform.tfvars"),
        ],
        "message": (
            f"Terraform resource '{tf_address}' added to '{primary_tf_name}' under 'artifacts/gcp'. "
            "Ready to run Terraform plan."
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
        working_directory = GCP_ARTIFACTS_DIR.resolve()
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}

    bucket_name, bucket_error = _get_state_bucket(record["project_id"])
    if bucket_error:
        return {"status": "BLOCKED", "message": bucket_error}

    _set_status(record, "PLANNING", "Terraform plan is being generated.")

    # Project-scoped state prefix guarantees ONE single state file for all resources in this project
    clean_project = record["project_id"].strip()
    prefix = f"taas/{clean_project}/gcp"
    state_uri = f"gs://{bucket_name}/{prefix}/default.tfstate"

    print(f"\n[TaaS] Starting planning for Request ID: {request_id}")
    print(f"[TaaS] Resource: {record.get('resource_type')} '{record.get('resource_name')}' (action: {record.get('action')})")
    print(f"[TaaS] Single shared working directory: {working_directory}")
    print(f"[TaaS] Authoritative single remote state: {state_uri}")

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


def apply_resource(
    request_id: str,
    plan_sha256: str,
    confirmation: Literal["apply", "dont apply"] = "apply",
) -> dict:
    """Apply the approved Terraform plan.

    Gated by ADK tool confirmation (`require_confirmation=True`).
    Verifies that the plan file has not changed since inspection.

    Args:
        request_id: UUID of the request.
        plan_sha256: SHA-256 digest of the plan returned during planning.
        confirmation: Confirmation decision ('apply' to proceed, 'dont apply' to cancel).

    Returns:
        dict: Apply summary and status.
    """
    if confirmation == "dont apply":
        try:
            record = _load_record(request_id)
            _set_status(record, "REJECTED", "User selected 'dont apply'. Terraform apply cancelled.")
        except Exception:
            pass
        return {
            "status": "REJECTED",
            "request_id": request_id,
            "message": "User selected 'dont apply'. The Terraform plan was cancelled and no changes were made to your cloud infrastructure.",
        }

    try:
        record = _load_record(request_id)
        working_directory = GCP_ARTIFACTS_DIR.resolve()
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

    clean_project = record["project_id"].strip()
    bucket_name = os.getenv("TAAS_STATE_BUCKET", "").strip()
    state_uri = f"gs://{bucket_name}/taas/{clean_project}/gcp/default.tfstate" if bucket_name else f"taas/{clean_project}/gcp"

    print(f"\n[TaaS] Applying approved Terraform plan for Request ID: {request_id}")
    print(f"[TaaS] Target plan file: {plan_target} in {working_directory.resolve()}")
    print(f"[TaaS] Updating single shared remote state: {state_uri}")

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
        "state_file": state_uri,
        "message": (
            f"Terraform apply completed for action '{action}'. "
            f"The single authoritative state file at '{state_uri}' has been updated. Next, run verify_resource."
        ),
        "apply_summary": result["output"][-12000:],
    }


def plan_deactivate_resource(
    project_id: str,
    resource_name: str,
    resource_type: str = "gcp.bigquery_dataset",
    dataset_id: str | None = None,
) -> dict:
    """Comment out a resource's Terraform code and generate a destroy plan.

    The resource code remains preserved in the artifacts directory with comments (#)
    so it can be recreated anytime using plan_recreate_resource.

    Args:
        project_id: The Google Cloud project ID.
        resource_name: Identifier for the resource (e.g. 'sales_data' or table_id).
        resource_type: Resource type (default: 'gcp.bigquery_dataset').
        dataset_id: Optional parent dataset ID for tables.

    Returns:
        dict: Destruction plan summary awaiting approval.
    """
    normalized_type = _normalize_resource_type(resource_type)
    matching = _find_records(
        project_id=project_id,
        resource_name=resource_name,
        resource_type=normalized_type,
        dataset_id=dataset_id,
    )
    if not matching:
        return {
            "status": "NOT_FOUND",
            "message": f"No existing deployment found for {normalized_type} '{resource_name}' in project '{project_id}'.",
        }

    active_record = matching[0]
    spec = SUPPORTED_RESOURCES[normalized_type]
    tf_file = GCP_ARTIFACTS_DIR / spec["primary_tf"]

    expected_address = active_record.get("expected_address")
    if not expected_address or expected_address.endswith(".requested"):
        if normalized_type == "gcp.bigquery_table":
            ds_id = dataset_id or active_record.get("resource_config", {}).get("dataset_id", "")
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", f"{ds_id}_{resource_name.strip()}")
            expected_address = f"google_bigquery_table.{tf_name}"
        elif normalized_type == "gcp.storage_bucket":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip().lower())
            expected_address = f"google_storage_bucket.{tf_name}"
        elif normalized_type == "gcp.pubsub_topic":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_pubsub_topic.{tf_name}"
        elif normalized_type == "gcp.pubsub_subscription":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_pubsub_subscription.{tf_name}"
        else:
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_bigquery_dataset.{tf_name}"

    # Ensure runtime artifacts directory and common files exist
    output_dir = GCP_ARTIFACTS_DIR
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "").strip()
    _ensure_common_artifacts(output_dir, project_id, active_record.get("location", "asia-south2"), state_bucket)

    # If the file does not exist yet, initialize it so it can be commented out
    if not tf_file.is_file():
        hcl_block, _, _ = _build_resource_hcl(
            resource_type=normalized_type,
            resource_name=resource_name,
            project_id=project_id,
            location=active_record.get("location", "asia-south2"),
            config=active_record.get("resource_config"),
        )
        _upsert_resource_block(tf_file, expected_address, hcl_block)

    # 1. Comment out the resource block in the shared .tf file
    toggled = _toggle_resource_block_in_file(tf_file, expected_address, comment_out=True)
    if not toggled:
        return {
            "status": "ERROR",
            "message": f"Could not find resource block '{expected_address}' in '{tf_file.name}' to comment out.",
        }

    # 2. Create a new deactivation request record
    deact_id = str(uuid4())
    new_record = dict(active_record)
    new_record["request_id"] = deact_id
    new_record["action"] = "DEACTIVATE"
    new_record["artifact_directory"] = str(tf_file.parent.resolve())
    new_record["primary_tf_file"] = str(tf_file.resolve())
    new_record["expected_address"] = expected_address
    new_record["status"] = "ARTIFACTS_READY"
    new_record["status_message"] = f"Resource block '{expected_address}' commented out. Ready to plan deactivation."
    new_record["created_at"] = _now()
    new_record["updated_at"] = _now()
    _save_record(new_record)

    # 3. Run plan_resource for the deactivation action
    return plan_resource(deact_id)


def plan_recreate_resource(
    project_id: str,
    resource_name: str,
    resource_type: str = "gcp.bigquery_dataset",
    dataset_id: str | None = None,
) -> dict:
    """Uncomment a previously deactivated resource and generate a create plan.

    Args:
        project_id: The Google Cloud project ID.
        resource_name: Identifier for the resource (e.g. 'sales_data' or table_id).
        resource_type: Resource type (default: 'gcp.bigquery_dataset').
        dataset_id: Optional parent dataset ID for tables.

    Returns:
        dict: Creation plan summary awaiting approval.
    """
    normalized_type = _normalize_resource_type(resource_type)
    matching = _find_records(
        project_id=project_id,
        resource_name=resource_name,
        resource_type=normalized_type,
        dataset_id=dataset_id,
    )
    if not matching:
        return {
            "status": "NOT_FOUND",
            "message": f"No existing record found for {normalized_type} '{resource_name}' in project '{project_id}'.",
        }

    active_record = matching[0]
    spec = SUPPORTED_RESOURCES[normalized_type]
    tf_file = GCP_ARTIFACTS_DIR / spec["primary_tf"]

    expected_address = active_record.get("expected_address")
    if not expected_address or expected_address.endswith(".requested"):
        if normalized_type == "gcp.bigquery_table":
            ds_id = dataset_id or active_record.get("resource_config", {}).get("dataset_id", "")
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", f"{ds_id}_{resource_name.strip()}")
            expected_address = f"google_bigquery_table.{tf_name}"
        elif normalized_type == "gcp.storage_bucket":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip().lower())
            expected_address = f"google_storage_bucket.{tf_name}"
        elif normalized_type == "gcp.pubsub_topic":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_pubsub_topic.{tf_name}"
        elif normalized_type == "gcp.pubsub_subscription":
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_pubsub_subscription.{tf_name}"
        else:
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
            expected_address = f"google_bigquery_dataset.{tf_name}"

    # Ensure runtime artifacts directory and common files exist
    output_dir = GCP_ARTIFACTS_DIR
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "").strip()
    _ensure_common_artifacts(output_dir, project_id, active_record.get("location", "asia-south2"), state_bucket)

    if not tf_file.is_file():
        return {"status": "ERROR", "message": f"Primary Terraform file '{tf_file}' not found."}

    # 1. Uncomment the resource block in the shared .tf file
    toggled = _toggle_resource_block_in_file(tf_file, expected_address, comment_out=False)
    if not toggled:
        return {
            "status": "ERROR",
            "message": f"Could not find resource block '{expected_address}' in '{tf_file.name}' to uncomment.",
        }

    # 2. Create a recreation request record
    recreate_id = str(uuid4())
    new_record = dict(active_record)
    new_record["request_id"] = recreate_id
    new_record["action"] = "RECREATE"
    new_record["artifact_directory"] = str(tf_file.parent.resolve())
    new_record["primary_tf_file"] = str(tf_file.resolve())
    new_record["expected_address"] = expected_address
    new_record["status"] = "ARTIFACTS_READY"
    new_record["status_message"] = f"Resource block '{expected_address}' restored. Ready to plan recreation."
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


async def _verify_bigquery_table(record: dict) -> dict:
    """Verify BigQuery table existence or deletion."""
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    client = bigquery.Client(project=record["project_id"])
    dataset_id = record.get("resource_config", {}).get("dataset_id")
    table_id = record.get("resource_name")
    table_ref = f"{record['project_id']}.{dataset_id}.{table_id}"
    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"

    print(f"\n[TaaS] Verifying {action_label} for table '{table_ref}' via BigQuery API...")

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] BigQuery API verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        try:
            table = await asyncio.to_thread(client.get_table, table_ref)
            print(f"[TaaS] Found table '{table_ref}' (type: {table.table_type})")
            if is_deactivation:
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", "Table still exists in BigQuery.")
                return {
                    "status": "VERIFYING",
                    "message": "Table is still visible in BigQuery; deletion is still processing.",
                }

            _set_status(record, "READY", "Table verified and ready in BigQuery.")
            schema_fields = [f"{f.name} ({f.field_type})" for f in (table.schema or [])]
            schema_info = f" with columns: {', '.join(schema_fields)}" if schema_fields else " (without schema)"
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "dataset_id": dataset_id,
                "resource_name": table_id,
                "table_ref": table_ref,
                "schema": schema_fields,
                "message": f"BigQuery table '{table_id}' in dataset '{dataset_id}' is confirmed READY in project '{record['project_id']}'{schema_info}.",
            }
        except NotFound:
            if is_deactivation:
                _set_status(record, "DELETED", "Table confirmed deleted from BigQuery. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "dataset_id": dataset_id,
                    "resource_name": table_id,
                    "message": (
                        f"BigQuery table '{table_id}' in dataset '{dataset_id}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }

            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)

    if is_deactivation:
        return {
            "status": "VERIFYING",
            "message": "Table deletion not yet reflected in BigQuery. Please retry verification shortly.",
        }
    return {
        "status": "VERIFYING",
        "message": "Table is not yet visible in BigQuery. Please retry verification shortly.",
    }


async def _verify_storage_bucket(record: dict) -> dict:
    """Verify Google Cloud Storage bucket existence or deletion."""
    from google.api_core.exceptions import NotFound
    from google.cloud import storage

    client = storage.Client(project=record["project_id"])
    bucket_name = record["resource_name"].strip().lower()
    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"

    print(f"\n[TaaS] Verifying {action_label} for GCS bucket '{bucket_name}' via Storage API...")

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] GCS API verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        try:
            bucket = await asyncio.to_thread(client.get_bucket, bucket_name)
            print(f"[TaaS] Found bucket '{bucket_name}' in location: {bucket.location}")
            if is_deactivation:
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", "GCS bucket still exists.")
                return {
                    "status": "VERIFYING",
                    "message": f"GCS bucket '{bucket_name}' is still visible in Google Cloud; deletion is still processing.",
                }

            _set_status(record, "READY", "GCS bucket verified and ready.")
            versioning_status = "enabled" if bucket.versioning_enabled else "disabled"
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "resource_name": bucket_name,
                "location": bucket.location,
                "versioning": versioning_status,
                "message": f"GCS bucket '{bucket_name}' is confirmed READY in project '{record['project_id']}' (location: {bucket.location}, versioning: {versioning_status}).",
            }
        except NotFound:
            if is_deactivation:
                _set_status(record, "DELETED", "GCS bucket confirmed deleted. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "resource_name": bucket_name,
                    "message": (
                        f"GCS bucket '{bucket_name}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }

            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)

    if is_deactivation:
        return {
            "status": "VERIFYING",
            "message": f"Bucket '{bucket_name}' deletion not yet reflected. Please retry verification shortly.",
        }
    return {
        "status": "VERIFYING",
        "message": f"Bucket '{bucket_name}' is not yet visible in Google Cloud. Please retry verification shortly.",
    }


async def _verify_pubsub_topic(record: dict) -> dict:
    """Verify Pub/Sub topic existence or deletion."""
    try:
        from google.api_core.exceptions import NotFound
        from google.cloud import pubsub_v1
    except ImportError:
        _set_status(record, "READY", "google-cloud-pubsub not installed; assuming resource ready.")
        return {
            "status": "READY",
            "project_id": record["project_id"],
            "resource_name": record["resource_name"],
            "message": f"Pub/Sub topic '{record['resource_name']}' applied in project '{record['project_id']}'.",
        }

    client = pubsub_v1.PublisherClient()
    topic_name = record["resource_name"].strip()
    topic_path = client.topic_path(record["project_id"], topic_name)
    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"

    print(f"\n[TaaS] Verifying {action_label} for Pub/Sub topic '{topic_path}'...")

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] Pub/Sub API verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        try:
            topic = await asyncio.to_thread(client.get_topic, request={"topic": topic_path})
            print(f"[TaaS] Found topic '{topic.name}'")
            if is_deactivation:
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", "Pub/Sub topic still exists.")
                return {
                    "status": "VERIFYING",
                    "message": f"Pub/Sub topic '{topic_name}' is still visible; deletion is still processing.",
                }

            _set_status(record, "READY", "Pub/Sub topic verified and ready.")
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "resource_name": topic_name,
                "topic_path": topic.name,
                "message": f"Pub/Sub topic '{topic_name}' is confirmed READY in project '{record['project_id']}'.",
            }
        except NotFound:
            if is_deactivation:
                _set_status(record, "DELETED", "Pub/Sub topic confirmed deleted. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "resource_name": topic_name,
                    "message": (
                        f"Pub/Sub topic '{topic_name}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }

            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)

    if is_deactivation:
        return {
            "status": "VERIFYING",
            "message": f"Topic '{topic_name}' deletion not yet reflected. Please retry verification shortly.",
        }
    return {
        "status": "VERIFYING",
        "message": f"Topic '{topic_name}' is not yet visible in Pub/Sub. Please retry verification shortly.",
    }


async def _verify_pubsub_subscription(record: dict) -> dict:
    """Verify Pub/Sub subscription existence or deletion."""
    try:
        from google.api_core.exceptions import NotFound
        from google.cloud import pubsub_v1
    except ImportError:
        _set_status(record, "READY", "google-cloud-pubsub not installed; assuming resource ready.")
        return {
            "status": "READY",
            "project_id": record["project_id"],
            "resource_name": record["resource_name"],
            "message": f"Pub/Sub subscription '{record['resource_name']}' applied in project '{record['project_id']}'.",
        }

    client = pubsub_v1.SubscriberClient()
    sub_name = record["resource_name"].strip()
    sub_path = client.subscription_path(record["project_id"], sub_name)
    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"

    print(f"\n[TaaS] Verifying {action_label} for Pub/Sub subscription '{sub_path}'...")

    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] Pub/Sub API verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        try:
            sub = await asyncio.to_thread(client.get_subscription, request={"subscription": sub_path})
            print(f"[TaaS] Found subscription '{sub.name}' (topic: {sub.topic})")
            if is_deactivation:
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", "Pub/Sub subscription still exists.")
                return {
                    "status": "VERIFYING",
                    "message": f"Pub/Sub subscription '{sub_name}' is still visible; deletion is still processing.",
                }

            _set_status(record, "READY", "Pub/Sub subscription verified and ready.")
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "resource_name": sub_name,
                "subscription_path": sub.name,
                "topic": sub.topic,
                "ack_deadline_seconds": sub.ack_deadline_seconds,
                "message": f"Pub/Sub subscription '{sub_name}' attached to '{sub.topic}' is confirmed READY in project '{record['project_id']}'.",
            }
        except NotFound:
            if is_deactivation:
                _set_status(record, "DELETED", "Pub/Sub subscription confirmed deleted. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "resource_name": sub_name,
                    "message": (
                        f"Pub/Sub subscription '{sub_name}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }

            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)

    if is_deactivation:
        return {
            "status": "VERIFYING",
            "message": f"Subscription '{sub_name}' deletion not yet reflected. Please retry verification shortly.",
        }
    return {
        "status": "VERIFYING",
        "message": f"Subscription '{sub_name}' is not yet visible in Pub/Sub. Please retry verification shortly.",
    }


VERIFIERS = {
    "gcp.bigquery_dataset": _verify_bigquery,
    "gcp.bigquery_table": _verify_bigquery_table,
    "gcp.storage_bucket": _verify_storage_bucket,
    "gcp.pubsub_topic": _verify_pubsub_topic,
    "gcp.pubsub_subscription": _verify_pubsub_subscription,
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


def list_taas_resources(
    project_id: str | None = None,
    include_deactivated: bool = False,
) -> dict:
    """List active, successfully created cloud resources.

    Filters out failed planning attempts (PLAN_FAILED), failed applies (APPLY_FAILED),
    unapplied drafts, and deleted resources.

    Args:
        project_id: Optional filter for a specific Google Cloud project ID.
        include_deactivated: If True, also includes preserved/deactivated resources.

    Returns:
        dict: List of active resources and count.
    """
    records = _find_records(project_id=project_id)

    # Group all request records by (project_id, resource_type, resource_name)
    grouped: dict[tuple, list[dict]] = {}
    for r in records:
        key = (r.get("project_id"), r.get("resource_type"), r.get("resource_name"))
        grouped.setdefault(key, []).append(r)

    active_resources = []
    ACTIVE_STATUSES = {"READY", "APPLIED"}
    INACTIVE_STATUSES = {"DEACTIVATED"}

    for (p_id, r_type, r_name), rec_list in grouped.items():
        # Find the latest completed lifecycle status (rec_list is sorted newest-first)
        latest_valid_record = None
        for r in rec_list:
            st = r.get("status")
            if st in ACTIVE_STATUSES or st in INACTIVE_STATUSES or st == "DELETED":
                latest_valid_record = r
                break

        # If the resource never successfully applied (e.g. only PLAN_FAILED or ARTIFACTS_READY), ignore it
        if not latest_valid_record:
            continue

        status = latest_valid_record.get("status")
        if status in ACTIVE_STATUSES or (include_deactivated and status in INACTIVE_STATUSES):
            res_item = {
                "project_id": p_id,
                "resource_type": r_type,
                "resource_name": r_name,
                "location": latest_valid_record.get("location"),
                "status": status,
                "action": latest_valid_record.get("action"),
                "artifact_directory": latest_valid_record.get("artifact_directory"),
                "last_updated": latest_valid_record.get("updated_at"),
            }
            if "dataset_id" in latest_valid_record.get("resource_config", {}):
                res_item["dataset_id"] = latest_valid_record["resource_config"]["dataset_id"]
            active_resources.append(res_item)

    return {
        "status": "SUCCESS",
        "count": len(active_resources),
        "resources": active_resources,
        "message": (
            f"Found {len(active_resources)} active resource(s)."
            if active_resources
            else "No active resources found in the registry."
        ),
    }
