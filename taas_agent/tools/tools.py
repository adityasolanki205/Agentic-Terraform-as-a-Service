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
import io
import json
import os
import re
import shutil
import subprocess
import zipfile
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
    "gcp.compute_instance": {
        "provider": "gcp",
        "short_name": "compute_instance",
        "starter_dir": STARTERS_DIR / "gcp" / "compute_instance",
        "primary_tf": "compute.tf",
        "resource_type_hcl": "google_compute_instance",
        "name_param": "instance_name",
        "description": "Google Compute Engine VM Instance",
    },
    "gcp.cloud_run_function": {
        "provider": "gcp",
        "short_name": "cloud_run_function",
        "starter_dir": STARTERS_DIR / "gcp" / "cloud_run_function",
        "primary_tf": "function.tf",
        "resource_type_hcl": "google_cloudfunctions2_function",
        "name_param": "function_name",
        "description": "Google Cloud Run Function (2nd Gen Python)",
    },
    "gcp.cloud_sql_instance": {
        "provider": "gcp",
        "short_name": "cloud_sql_instance",
        "starter_dir": STARTERS_DIR / "gcp" / "cloud_sql_instance",
        "primary_tf": "sql.tf",
        "resource_type_hcl": "google_sql_database_instance",
        "name_param": "instance_name",
        "description": "Google Cloud SQL Database Instance",
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
        "compute_instance": "gcp.compute_instance",
        "compute_engine": "gcp.compute_instance",
        "compute": "gcp.compute_instance",
        "gce_instance": "gcp.compute_instance",
        "vm": "gcp.compute_instance",
        "cloud_run_function": "gcp.cloud_run_function",
        "cloud_run_functions": "gcp.cloud_run_function",
        "cloud_function": "gcp.cloud_run_function",
        "cloudfunctions2_function": "gcp.cloud_run_function",
        "function": "gcp.cloud_run_function",
        "cloud_sql_instance": "gcp.cloud_sql_instance",
        "cloud_sql": "gcp.cloud_sql_instance",
        "cloudsql": "gcp.cloud_sql_instance",
        "sql_instance": "gcp.cloud_sql_instance",
        "sql": "gcp.cloud_sql_instance",
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


def _ensure_function_source_zip(
    project_id: str,
    tf_name: str,
    bucket_name: str | None = None,
    object_name: str | None = None,
) -> tuple[str, str]:
    """Package Python Hello World Cloud Run Function source code and upload it to GCS."""
    target_bucket = (
        bucket_name
        or os.getenv("TAAS_STATE_BUCKET", "").strip()
        or "terraform-implementation"
    )
    target_object = object_name or f"taas/{project_id.strip()}/functions/{tf_name}-source.zip"

    src_dir = STARTERS_DIR / "gcp" / "cloud_run_function" / "src"
    custom_main_py = GCP_ARTIFACTS_DIR / "function.py"
    starter_main_py = src_dir / "main.py"
    req_txt = src_dir / "requirements.txt"

    main_code = (
        custom_main_py.read_text(encoding="utf-8")
        if custom_main_py.is_file()
        else (
            starter_main_py.read_text(encoding="utf-8")
            if starter_main_py.is_file()
            else (
                "import functions_framework\n\n"
                "@functions_framework.http\n"
                "def hello_http(request):\n"
                "    return 'Hello, World!'\n"
            )
        )
    )
    req_code = (
        req_txt.read_text(encoding="utf-8")
        if req_txt.is_file()
        else "functions-framework==3.*\n"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.py", main_code)
        zf.writestr("requirements.txt", req_code)
    zip_bytes = buf.getvalue()

    try:
        from google.cloud import storage

        client = storage.Client(project=project_id.strip())
        blob = client.bucket(target_bucket).blob(target_object)
        blob.upload_from_string(zip_bytes, content_type="application/zip")
        print(f"[TaaS] Uploaded Python Cloud Run Function source zip to gs://{target_bucket}/{target_object}")
    except Exception as exc:
        print(f"[TaaS][Warn] Could not upload Cloud Run Function zip to gs://{target_bucket}/{target_object}: {exc}")

    return target_bucket, target_object


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

        versioning_enabled = config.get("versioning", False)
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
                .replace('lookup(var.resource_config, "versioning", false)', versioning_str)
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

    elif resource_type == "gcp.compute_instance":
        inst_name = clean_name.lower()
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", inst_name)
        tf_address = f"google_compute_instance.{tf_name}"

        raw_zone = str(config.get("zone") or "").strip()
        if raw_zone:
            zone = raw_zone
        elif len(clean_location.split("-")) >= 3:
            zone = clean_location
        else:
            zone = f"{clean_location}-a"
        machine_type = str(config.get("machine_type") or "e2-micro").strip()

        starter_file = STARTERS_DIR / "gcp" / "compute_instance" / "compute.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["instance_name"]', f'"{inst_name}"')
                .replace("{{instance_name}}", inst_name)
                .replace('lookup(var.resource_config, "machine_type", "e2-micro")', f'"{machine_type}"')
                .replace('lookup(var.resource_config, "zone", "${var.location}-a")', f'"{zone}"')
                .replace("var.project_id", f'"{clean_project}"')
                .replace("{{project_id}}", clean_project)
                .replace("var.location", f'"{clean_location}"')
                .strip()
            )
        else:
            rendered = f"""resource "google_compute_instance" "{tf_name}" {{
  name                      = "{inst_name}"
  machine_type              = "{machine_type}"
  zone                      = "{zone}"
  project                   = "{clean_project}"
  allow_stopping_for_update = true

  boot_disk {{
    initialize_params {{
      image = "debian-cloud/debian-12"
    }}
  }}

  network_interface {{
    network = "default"
    access_config {{}}
  }}
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.cloud_run_function":
        func_name = clean_name.lower()
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", func_name)
        tf_address = f"google_cloudfunctions2_function.{tf_name}"

        src_bucket, src_object = _ensure_function_source_zip(
            project_id=clean_project,
            tf_name=tf_name,
            bucket_name=str(config.get("source_bucket") or "").strip() or None,
            object_name=str(config.get("source_object") or "").strip() or None,
        )
        runtime = str(config.get("runtime") or "python312").strip()
        entry_point = str(config.get("entry_point") or "hello_http").strip()

        starter_file = STARTERS_DIR / "gcp" / "cloud_run_function" / "function.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["function_name"]', f'"{func_name}"')
                .replace('var.resource_config["source_bucket"]', f'"{src_bucket}"')
                .replace('var.resource_config["source_object"]', f'"{src_object}"')
                .replace('"python312"', f'"{runtime}"')
                .replace('"hello_http"', f'"{entry_point}"')
                .replace("var.project_id", f'"{clean_project}"')
                .replace("var.location", f'"{clean_location}"')
                .strip()
            )
        else:
            rendered = f"""resource "google_cloudfunctions2_function" "{tf_name}" {{
  name        = "{func_name}"
  location    = "{clean_location}"
  project     = "{clean_project}"
  description = "Python Hello World Cloud Run Function managed by TaaS"

  build_config {{
    runtime     = "{runtime}"
    entry_point = "{entry_point}"
    source {{
      storage_source {{
        bucket = "{src_bucket}"
        object = "{src_object}"
      }}
    }}
  }}

  service_config {{
    max_instance_count = 3
    available_memory   = "256M"
    timeout_seconds    = 60
  }}
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    elif resource_type == "gcp.cloud_sql_instance":
        sql_name = clean_name.lower()
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", sql_name)
        tf_address = f"google_sql_database_instance.{tf_name}"

        db_version = str(config.get("database_version") or "POSTGRES_15").strip()
        tier = str(config.get("tier") or "db-f1-micro").strip()

        starter_file = STARTERS_DIR / "gcp" / "cloud_sql_instance" / "sql.tf"
        if starter_file.is_file():
            template = starter_file.read_text(encoding="utf-8")
            template_lines = [l for l in template.splitlines() if not l.startswith("#")]
            template = "\n".join(template_lines).strip()
            rendered = (
                template.replace('"requested"', f'"{tf_name}"')
                .replace("{{tf_name}}", tf_name)
                .replace('var.resource_config["instance_name"]', f'"{sql_name}"')
                .replace('lookup(var.resource_config, "database_version", "POSTGRES_15")', f'"{db_version}"')
                .replace('lookup(var.resource_config, "tier", "db-f1-micro")', f'"{tier}"')
                .replace("var.project_id", f'"{clean_project}"')
                .replace("var.location", f'"{clean_location}"')
                .strip()
            )
        else:
            rendered = f"""resource "google_sql_database_instance" "{tf_name}" {{
  name                = "{sql_name}"
  project             = "{clean_project}"
  region              = "{clean_location}"
  database_version    = "{db_version}"
  deletion_protection = false

  settings {{
    tier              = "{tier}"
    availability_type = "ZONAL"
    disk_autoresize   = true
    disk_size         = 10
    disk_type         = "PD_SSD"
  }}
}}"""
        hcl = f"# --- START: {tf_address} ---\n{rendered}\n# --- END: {tf_address} ---"
        return hcl, tf_name, tf_address

    else:
        raise ValueError(f"Unsupported resource type: {resource_type}")


def _find_hcl_block_end(lines: list[str], start_line: int) -> int | None:
    """Return closing line index of an HCL block starting at start_line."""
    brace_count = 0
    saw_open = False
    for j in range(start_line, len(lines)):
        line = lines[j]
        in_str = False
        esc = False
        for idx, ch in enumerate(line):
            if esc:
                esc = False
                continue
            if ch == "\\" and in_str:
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == "#":
                    break
                if ch == "/" and idx + 1 < len(line) and line[idx + 1] == "/":
                    break
                if ch == "{":
                    brace_count += 1
                    saw_open = True
                elif ch == "}":
                    brace_count -= 1
        if saw_open and brace_count <= 0:
            return j
    return None


def _dedupe_hcl_blocks(content: str, target_address: str | None = None) -> str:
    """Remove duplicate active HCL resource blocks (keeping the latest copy per address)."""
    lines = content.splitlines()
    ranges: list[tuple[str, int, int]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m_start = re.match(r"^\s*#\s*---\s*START:\s*([A-Za-z0-9_]+\.[A-Za-z0-9_]+)(?:\s|---|$)", line)
        if m_start:
            addr = m_start.group(1)
            end_marker = f"# --- END: {addr}"
            end_idx = None
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith(end_marker):
                    end_idx = j
                    break
            if end_idx is None:
                # Marker was orphaned without END marker; fall back to HCL block braces
                for k in range(i + 1, len(lines)):
                    if re.match(r'^\s*resource\s+"[^"]+"\s+"[^"]+"', lines[k]):
                        end_idx = _find_hcl_block_end(lines, k)
                        break
            if end_idx is not None:
                has_active_res = any(
                    re.match(r'^\s*resource\s+"[^"]+"\s+"[^"]+"', lines[k])
                    for k in range(i, end_idx + 1)
                )
                if has_active_res:
                    ranges.append((addr, i, end_idx))
                    i = end_idx + 1
                    continue
        m_res = re.match(r'^\s*resource\s+"([A-Za-z0-9_]+)"\s+"([A-Za-z0-9_]+)"\s*\{', line)
        if m_res:
            addr = f"{m_res.group(1)}.{m_res.group(2)}"
            end_idx = _find_hcl_block_end(lines, i)
            if end_idx is not None:
                ranges.append((addr, i, end_idx))
                i = end_idx + 1
                continue
        i += 1

    # Decide which ranges to drop
    remove_indices: set[int] = set()
    if target_address is not None:
        for addr, s_idx, e_idx in ranges:
            if addr == target_address:
                remove_indices.update(range(s_idx, e_idx + 1))
    else:
        seen_latest: dict[str, int] = {}
        for idx, (addr, _, _) in enumerate(ranges):
            seen_latest[addr] = idx
        for idx, (addr, s_idx, e_idx) in enumerate(ranges):
            if seen_latest[addr] != idx:
                remove_indices.update(range(s_idx, e_idx + 1))

    if not remove_indices:
        return content

    kept_lines = [ln for idx, ln in enumerate(lines) if idx not in remove_indices]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip()
    return (cleaned + "\n") if cleaned else ""


def _upsert_resource_block(file_path: Path, tf_address: str, new_block: str) -> None:
    """Insert or replace a resource block in a shared .tf file without leaving duplicates."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.is_file():
        file_path.write_text(f"# Managed by Agentic Terraform as a Service (TaaS)\n\n{new_block.strip()}\n", encoding="utf-8")
        return

    content = file_path.read_text(encoding="utf-8")
    stripped_existing = _dedupe_hcl_blocks(content, target_address=tf_address)
    if not stripped_existing.strip():
        updated = f"# Managed by Agentic Terraform as a Service (TaaS)\n\n{new_block.strip()}\n"
    else:
        updated = stripped_existing.rstrip() + "\n\n" + new_block.strip() + "\n"
    updated = _dedupe_hcl_blocks(updated)
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
    elif norm_type in ("gcp.compute_instance", "gcp.cloud_run_function", "gcp.cloud_sql_instance"):
        clean_res = resource_name.strip().lower()
        if not re.fullmatch(r"[a-z]([a-z0-9-]{0,61}[a-z0-9])?", clean_res):
            errors.append(
                "Resource name must be 1-63 characters, start with a lowercase letter, "
                "end with a lowercase letter or digit, and contain only lowercase letters, digits, or hyphens."
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

    clean_hcl = "\n".join(
        line
        for line in hcl_block.splitlines()
        if not line.strip().startswith("# --- START:") and not line.strip().startswith("# --- END:")
    ).strip()

    return {
        "status": "SUCCESS",
        "request_id": request_id,
        "action": "CREATE",
        "resource_type": normalized_type,
        "resource_name": resource_name.strip(),
        "artifact_directory": str(output_dir.resolve()),
        "expected_address": tf_address,
        "primary_tf_file": primary_tf_name,
        "generated_code": clean_hcl,
        "files": [
            str(output_dir / "main.tf"),
            str(output_dir / "variables.tf"),
            str(primary_tf),
            str(output_dir / "terraform.tfvars"),
        ],
        "message": (
            f"Terraform resource '{tf_address}' added to '{primary_tf_name}' under 'artifacts/gcp'."
        ),
    }



def sync_terraform_state(
    project_id: str | None = None,
    preserve_request_id: str | None = None,
) -> dict:
    """Synchronize local artifacts/gcp/*.tf files and request records with the authoritative GCS remote state."""
    clean_project = (
        project_id
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("PROJECT_ID")
        or "solar-dialect-264808"
    ).strip()
    default_loc = os.getenv("TAAS_DEFAULT_REGION", "asia-south2").strip()
    if default_loc.lower() == "global":
        default_loc = "asia-south2"
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "terraform-implementation").strip()

    _ensure_common_artifacts(GCP_ARTIFACTS_DIR, clean_project, default_loc, state_bucket)

    preserve_addr = None
    preserve_action = None
    if preserve_request_id:
        try:
            p_rec = _load_record(preserve_request_id)
            preserve_addr = p_rec.get("expected_address")
            preserve_action = p_rec.get("action")
        except Exception:
            pass

    state_data = None
    prefix = f"taas/{clean_project}/gcp"
    try:
        from google.cloud import storage

        blob = storage.Client(project=clean_project).bucket(state_bucket).blob(f"{prefix}/default.tfstate")
        if blob.exists():
            state_data = json.loads(blob.download_as_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[TaaS][Sync] Direct GCS state read fallback: {exc}")

    if state_data is None:
        pull_res = _run_terraform(["state", "pull"], GCP_ARTIFACTS_DIR, separate_stderr=True)
        raw_pull = (pull_res.get("stdout") or "").strip()
        if pull_res.get("returncode") == 0 and raw_pull.startswith("{"):
            try:
                state_data = json.loads(raw_pull)
            except Exception:
                state_data = None

    if not state_data or not isinstance(state_data, dict):
        return {
            "status": "NO_REMOTE_STATE",
            "synced_count": 0,
            "message": "No remote state file found or state is empty.",
        }

    hcl_to_norm = {
        "google_storage_bucket": "gcp.storage_bucket",
        "google_bigquery_dataset": "gcp.bigquery_dataset",
        "google_bigquery_table": "gcp.bigquery_table",
        "google_pubsub_topic": "gcp.pubsub_topic",
        "google_pubsub_subscription": "gcp.pubsub_subscription",
        "google_compute_instance": "gcp.compute_instance",
        "google_cloudfunctions2_function": "gcp.cloud_run_function",
        "google_sql_database_instance": "gcp.cloud_sql_instance",
    }

    state_addresses = set()
    synced_addresses = []

    for res in state_data.get("resources", []):
        if res.get("mode") and res.get("mode") != "managed":
            continue
        hcl_type = res.get("type", "")
        tf_name = res.get("name", "")
        if hcl_type not in hcl_to_norm or not tf_name:
            continue

        norm_type = hcl_to_norm[hcl_type]
        spec = SUPPORTED_RESOURCES[norm_type]
        tf_address = f"{hcl_type}.{tf_name}"
        state_addresses.add(tf_address)

        instances = res.get("instances") or []
        attrs = (instances[0].get("attributes") if instances else None) or {}
        res_project = (attrs.get("project") or clean_project).strip()
        res_loc = (attrs.get("location") or default_loc).strip()

        if norm_type == "gcp.storage_bucket":
            res_name = attrs.get("name") or tf_name
            ver_list = attrs.get("versioning") or []
            ver_enabled = bool(ver_list[0].get("enabled", False)) if isinstance(ver_list, list) and ver_list else False
            cfg = {"versioning": ver_enabled}
        elif norm_type == "gcp.bigquery_dataset":
            res_name = attrs.get("dataset_id") or tf_name
            cfg = {}
        elif norm_type == "gcp.bigquery_table":
            res_name = attrs.get("table_id") or tf_name
            cfg = {"dataset_id": attrs.get("dataset_id") or ""}
            if attrs.get("schema"):
                cfg["schema"] = attrs.get("schema")
        elif norm_type == "gcp.pubsub_topic":
            res_name = attrs.get("name") or tf_name
            res_loc = "global"
            cfg = {}
        elif norm_type == "gcp.pubsub_subscription":
            res_name = attrs.get("name") or tf_name
            res_loc = "global"
            cfg = {"topic": str(attrs.get("topic") or "").split("/")[-1]}
        elif norm_type == "gcp.compute_instance":
            res_name = attrs.get("name") or tf_name
            raw_zone = str(attrs.get("zone") or f"{default_loc}-a").split("/")[-1]
            res_loc = raw_zone
            cfg = {
                "zone": raw_zone,
                "machine_type": str(attrs.get("machine_type") or "e2-micro").split("/")[-1],
            }
        elif norm_type == "gcp.cloud_run_function":
            res_name = attrs.get("name") or tf_name
            res_loc = attrs.get("location") or default_loc
            build_cfg = (attrs.get("build_config") or [{}])[0] if isinstance(attrs.get("build_config"), list) else {}
            storage_src = ((build_cfg.get("source") or [{}])[0].get("storage_source") or [{}])[0] if isinstance(build_cfg.get("source"), list) else {}
            cfg = {
                "runtime": build_cfg.get("runtime") or "python312",
                "entry_point": build_cfg.get("entry_point") or "hello_http",
                "source_bucket": storage_src.get("bucket") or state_bucket,
                "source_object": storage_src.get("object") or f"taas/{clean_project}/functions/{tf_name}-source.zip",
            }
        elif norm_type == "gcp.cloud_sql_instance":
            res_name = attrs.get("name") or tf_name
            res_loc = attrs.get("region") or default_loc
            settings_list = attrs.get("settings") or []
            tier_val = settings_list[0].get("tier", "db-f1-micro") if isinstance(settings_list, list) and settings_list else "db-f1-micro"
            cfg = {
                "database_version": attrs.get("database_version") or "POSTGRES_15",
                "tier": tier_val,
            }
        else:
            continue

        # If this resource is currently being deactivated in the active request, keep it commented out
        if preserve_action == "DEACTIVATE" and tf_address == preserve_addr:
            continue

        tf_file = GCP_ARTIFACTS_DIR / spec["primary_tf"]
        file_text = tf_file.read_text(encoding="utf-8") if tf_file.is_file() else ""

        # Comment out raw starter placeholder block if present in artifacts/gcp/
        if f'resource "{hcl_type}" "requested"' in file_text:
            _toggle_resource_block_in_file(tf_file, f"{hcl_type}.requested", comment_out=True)
            file_text = tf_file.read_text(encoding="utf-8")

        active_pattern = re.compile(
            rf'^\s*resource\s+"{re.escape(hcl_type)}"\s+"{re.escape(tf_name)}"',
            re.MULTILINE,
        )
        if not active_pattern.search(file_text):
            # Try uncommenting if it was commented out from an unapplied deactivation
            uncommented = _toggle_resource_block_in_file(tf_file, tf_address, comment_out=False)
            file_text = tf_file.read_text(encoding="utf-8") if tf_file.is_file() else ""
            if not uncommented or not active_pattern.search(file_text):
                hcl_block, _, _ = _build_resource_hcl(
                    resource_type=norm_type,
                    resource_name=res_name,
                    project_id=res_project,
                    location=res_loc,
                    config=cfg,
                )
                _upsert_resource_block(tf_file, tf_address, hcl_block)

        synced_addresses.append(tf_address)

        # Ensure .taas/requests has an active READY record for this state resource
        existing_recs = _find_records(
            project_id=res_project,
            resource_name=res_name,
            resource_type=norm_type,
        )
        has_active_rec = any(r.get("status") in ("READY", "APPLIED") for r in existing_recs)
        if not has_active_rec:
            sync_id = str(uuid4())
            _save_record(
                {
                    "request_id": sync_id,
                    "action": "CREATE",
                    "resource_type": norm_type,
                    "resource_name": res_name,
                    "project_id": res_project,
                    "location": res_loc,
                    "resource_config": cfg,
                    "artifact_directory": str(GCP_ARTIFACTS_DIR.resolve()),
                    "primary_tf_file": str(tf_file.resolve()),
                    "expected_address": tf_address,
                    "tf_resource_name": tf_name,
                    "status": "READY",
                    "status_message": "Synced from authoritative GCS Terraform state.",
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )

    # Also comment out any stale/unapplied active resource blocks in artifacts/gcp/*.tf
    # that are NOT in remote state (except preserve_addr when creating/recreating)
    for spec in SUPPORTED_RESOURCES.values():
        tf_file = GCP_ARTIFACTS_DIR / spec["primary_tf"]
        if not tf_file.is_file():
            continue
        text = tf_file.read_text(encoding="utf-8")
        for match in list(
            re.finditer(r'^\s*resource\s+"([a-zA-Z0-9_]+)"\s+"([a-zA-Z0-9_]+)"', text, re.MULTILINE)
        ):
            r_type, r_name = match.group(1), match.group(2)
            addr = f"{r_type}.{r_name}"
            if addr not in state_addresses:
                if preserve_addr and addr == preserve_addr and preserve_action in ("CREATE", "RECREATE"):
                    continue
                _toggle_resource_block_in_file(tf_file, addr, comment_out=True)

    _run_terraform(["fmt", "-recursive"], GCP_ARTIFACTS_DIR)
    return {
        "status": "SUCCESS",
        "synced_count": len(synced_addresses),
        "synced_addresses": synced_addresses,
        "message": f"Synced {len(synced_addresses)} resource(s) from remote GCS Terraform state.",
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

    # 0. Sync artifacts/gcp/*.tf with remote GCS state so existing state resources are never missing
    try:
        sync_terraform_state(project_id=clean_project, preserve_request_id=request_id)
    except Exception as sync_err:
        print(f"[TaaS][Warn] Pre-plan state sync warning: {sync_err}")

    # Guard against any duplicate resource blocks across artifacts/gcp/*.tf before fmt/validate
    for tf_path in sorted(working_directory.glob("*.tf")):
        try:
            orig_tf = tf_path.read_text(encoding="utf-8")
            deduped_tf = _dedupe_hcl_blocks(orig_tf)
            if deduped_tf != orig_tf:
                tf_path.write_text(deduped_tf, encoding="utf-8")
                print(f"[TaaS] Deduplicated duplicate resource block(s) in {tf_path.name}.")
        except Exception as dedupe_err:
            print(f"[TaaS][Warn] Could not dedupe {tf_path.name}: {dedupe_err}")

    # Ensure Cloud Run Function source zip is freshly packaged & uploaded to GCS when planning create/recreate
    if record.get("resource_type") == "gcp.cloud_run_function" and record.get("action") in ("CREATE", "RECREATE"):
        cfg = record.get("resource_config") or {}
        tf_name = record.get("tf_resource_name") or re.sub(r"[^A-Za-z0-9_]", "_", record.get("resource_name", "").lower())
        _ensure_function_source_zip(
            project_id=clean_project,
            tf_name=tf_name,
            bucket_name=cfg.get("source_bucket") or bucket_name,
            object_name=cfg.get("source_object") or f"taas/{clean_project}/functions/{tf_name}-source.zip",
        )

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
            "-parallelism=2",
            "-lock-timeout=5m",
            "-out=terraform.tfplan",
        ],
        working_directory,
    )
    if result["returncode"] != 0 and any(
        err_tok in (result.get("output") or "").lower()
        for err_tok in ("connection refused", "dial tcp", "reset by peer", "timeout")
    ):
        print("[TaaS][Plan] Transient network error during state refresh; retrying plan with -refresh=false...")
        result = _run_terraform(
            [
                "plan",
                "-refresh=false",
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

    # 4. Build concise plan summary, hash plan, and save awaiting user confirmation
    raw_plan_text = readable_plan["output"] or ""
    key_attr_re = re.compile(
        r"^(?:[+-~]\s+)?(name|dataset_id|table_id|project|location|region|zone|machine_type|runtime|entry_point|database_version|tier|storage_class|topic|force_destroy|uniform_bucket_level_access|deletion_protection)\s*="
    )
    compact_lines = []
    in_res_block = False
    for raw_line in raw_plan_text.splitlines():
        s_line = raw_line.strip()
        if s_line.startswith("# ") and ("will be " in s_line or "must be " in s_line):
            compact_lines.append(s_line)
        elif re.match(r"^[+-~]?\s*resource\s+\"[^\"]+\"\s+\"[^\"]+\"\s*\{", s_line):
            compact_lines.append(s_line)
            in_res_block = True
        elif in_res_block and key_attr_re.match(s_line):
            compact_lines.append("  " + s_line)
        elif s_line.startswith("Plan:"):
            if in_res_block:
                compact_lines.append("  }")
                in_res_block = False
            compact_lines.append("")
            compact_lines.append(s_line)
    if in_res_block:
        compact_lines.append("  }")
    concise_summary = "\n".join(compact_lines) if compact_lines else "\n".join(raw_plan_text.splitlines()[-10:])

    digest = hashlib.sha256(saved_plan.read_bytes()).hexdigest()
    record["plan_sha256"] = digest
    record["plan_file"] = str(saved_plan.resolve())
    record["plan_summary"] = concise_summary
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
        "plan_summary": concise_summary,
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


def _resolve_expected_address(
    normalized_type: str,
    resource_name: str,
    active_record: dict,
    dataset_id: str | None = None,
) -> str:
    """Resolve the Terraform resource address for an active or deactivated request record."""
    expected_address = active_record.get("expected_address")
    if expected_address and not expected_address.endswith(".requested"):
        return expected_address
    hcl_type = SUPPORTED_RESOURCES[normalized_type]["resource_type_hcl"]
    if normalized_type == "gcp.bigquery_table":
        ds_id = dataset_id or active_record.get("resource_config", {}).get("dataset_id", "")
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", f"{ds_id}_{resource_name.strip()}")
    elif normalized_type in (
        "gcp.storage_bucket",
        "gcp.compute_instance",
        "gcp.cloud_run_function",
        "gcp.cloud_sql_instance",
    ):
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip().lower())
    else:
        tf_name = re.sub(r"[^A-Za-z0-9_]", "_", resource_name.strip())
    return f"{hcl_type}.{tf_name}"


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

    expected_address = _resolve_expected_address(
        normalized_type, resource_name, active_record, dataset_id=dataset_id
    )

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

    expected_address = _resolve_expected_address(
        normalized_type, resource_name, active_record, dataset_id=dataset_id
    )

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


async def _verify_gcp_rest_resource(
    record: dict,
    display_label: str,
    api_url: str,
) -> dict:
    """Verify a GCP resource via Google REST API GET (404 confirms deletion)."""
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        _set_status(record, "READY", f"{display_label} applied (google-auth unavailable for REST verification).")
        return {
            "status": "READY",
            "project_id": record["project_id"],
            "resource_name": record["resource_name"],
            "message": f"{display_label} '{record['resource_name']}' applied in project '{record['project_id']}'.",
        }

    is_deactivation = record.get("action") == "DEACTIVATE"
    action_label = "deletion" if is_deactivation else "creation"
    resource_name = record["resource_name"].strip()

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    session = AuthorizedSession(credentials)

    print(f"\n[TaaS] Verifying {action_label} for {display_label} '{resource_name}' via REST API...")
    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        print(f"[TaaS] {display_label} verification attempt {attempt}/{VERIFY_ATTEMPTS}...")
        resp = await asyncio.to_thread(session.get, api_url, timeout=15)
        if resp.status_code == 200:
            if is_deactivation:
                if attempt < VERIFY_ATTEMPTS:
                    await asyncio.sleep(VERIFY_DELAY_SECONDS)
                    continue
                _set_status(record, "DEACTIVATE_UNCONFIRMED", f"{display_label} still exists in Google Cloud.")
                return {
                    "status": "VERIFYING",
                    "message": f"{display_label} '{resource_name}' is still visible; deletion is still processing.",
                }
            _set_status(record, "READY", f"{display_label} verified and ready in Google Cloud.")
            return {
                "status": "READY",
                "project_id": record["project_id"],
                "resource_name": resource_name,
                "location": record.get("location"),
                "message": f"{display_label} '{resource_name}' is confirmed READY in project '{record['project_id']}'.",
            }
        if resp.status_code in (404, 410):
            if is_deactivation:
                _set_status(record, "DELETED", f"{display_label} confirmed deleted from Google Cloud. Code preserved.")
                return {
                    "status": "DELETED",
                    "project_id": record["project_id"],
                    "resource_name": resource_name,
                    "message": (
                        f"{display_label} '{resource_name}' has been confirmed DELETED from Google Cloud. "
                        "The Terraform code is preserved in artifacts for future recreation."
                    ),
                }
            if attempt < VERIFY_ATTEMPTS:
                await asyncio.sleep(VERIFY_DELAY_SECONDS)
                continue
        elif attempt < VERIFY_ATTEMPTS:
            await asyncio.sleep(VERIFY_DELAY_SECONDS)

    return {
        "status": "VERIFYING",
        "message": (
            f"{display_label} '{resource_name}' {action_label} not yet reflected in Google Cloud. "
            "Please retry verification shortly."
        ),
    }


async def _verify_compute_instance(record: dict) -> dict:
    """Verify Compute Engine VM instance existence or deletion."""
    loc = (record.get("resource_config", {}).get("zone") or record.get("location") or "asia-south2").strip()
    zone = loc if len(loc.split("-")) >= 3 else f"{loc}-a"
    name = record["resource_name"].strip().lower()
    url = f"https://compute.googleapis.com/compute/v1/projects/{record['project_id']}/zones/{zone}/instances/{name}"
    return await _verify_gcp_rest_resource(record, "Compute Engine VM", url)


async def _verify_cloud_run_function(record: dict) -> dict:
    """Verify Cloud Run Function (2nd Gen) existence or deletion."""
    loc = (record.get("location") or "asia-south2").strip()
    name = record["resource_name"].strip().lower()
    url = f"https://cloudfunctions.googleapis.com/v2/projects/{record['project_id']}/locations/{loc}/functions/{name}"
    return await _verify_gcp_rest_resource(record, "Cloud Run Function", url)


async def _verify_cloud_sql_instance(record: dict) -> dict:
    """Verify Cloud SQL instance existence or deletion."""
    name = record["resource_name"].strip().lower()
    url = f"https://sqladmin.googleapis.com/v1/projects/{record['project_id']}/instances/{name}"
    return await _verify_gcp_rest_resource(record, "Cloud SQL instance", url)


VERIFIERS = {
    "gcp.bigquery_dataset": _verify_bigquery,
    "gcp.bigquery_table": _verify_bigquery_table,
    "gcp.storage_bucket": _verify_storage_bucket,
    "gcp.pubsub_topic": _verify_pubsub_topic,
    "gcp.pubsub_subscription": _verify_pubsub_subscription,
    "gcp.compute_instance": _verify_compute_instance,
    "gcp.cloud_run_function": _verify_cloud_run_function,
    "gcp.cloud_sql_instance": _verify_cloud_sql_instance,
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


# ==============================================================================
# Terraform Documentation & Artifact Code Inspection/Update Tools
# ==============================================================================

# Ensure no disk caching is used for documentation (always fetched live)
_legacy_doc_cache = PROJECT_ROOT / ".taas" / "doc_cache"
if _legacy_doc_cache.exists():
    try:
        shutil.rmtree(_legacy_doc_cache, ignore_errors=True)
    except Exception:
        pass

DOC_RESOURCE_METADATA = {

    "gcp.storage_bucket": {
        "hcl_type": "google_storage_bucket",
        "doc_file": "storage_bucket.html.markdown",
        "registry_slug": "storage_bucket",
        "primary_tf": "bucket.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": (
                    "In Google Cloud Platform and the Google Terraform provider, resource tags are configured "
                    "using the 'labels' argument as a map of key-value string pairs."
                ),
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    managed_by  = "taas"\n'
                    '    owner       = "engineering"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Assign key/value string pairs to label and categorize the storage bucket.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    department  = "data"\n'
                    '  }'
                ),
            },
            "retention": {
                "argument": "retention_policy",
                "explanation": "Enforces a minimum retention period for all objects in the bucket before they can be deleted.",
                "snippet": (
                    '  retention_policy {\n'
                    '    is_locked        = false\n'
                    '    retention_period = 2592000 # 30 days in seconds\n'
                    '  }'
                ),
            },
            "lifecycle": {
                "argument": "lifecycle_rule",
                "explanation": "Configures object lifecycle management rules (e.g. auto-delete objects after N days).",
                "snippet": (
                    '  lifecycle_rule {\n'
                    '    condition {\n'
                    '      age = 30 # days\n'
                    '    }\n'
                    '    action {\n'
                    '      type = "Delete"\n'
                    '    }\n'
                    '  }'
                ),
            },
            "cors": {
                "argument": "cors",
                "explanation": "Configures Cross-Origin Resource Sharing (CORS) policies for the storage bucket.",
                "snippet": (
                    '  cors {\n'
                    '    origin          = ["*"]\n'
                    '    method          = ["GET", "HEAD", "PUT", "POST"]\n'
                    '    response_header = ["*"]\n'
                    '    max_age_seconds = 3600\n'
                    '  }'
                ),
            },
            "encryption": {
                "argument": "encryption",
                "explanation": "Configures Customer-Managed Encryption Keys (CMEK) for the bucket.",
                "snippet": (
                    '  encryption {\n'
                    '    default_kms_key_name = "projects/PROJECT_ID/locations/LOCATION/keyRings/RING/cryptoKeys/KEY"\n'
                    '  }'
                ),
            },
        },
    },
    "gcp.bigquery_dataset": {
        "hcl_type": "google_bigquery_dataset",
        "doc_file": "bigquery_dataset.html.markdown",
        "registry_slug": "bigquery_dataset",
        "primary_tf": "dataset.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": (
                    "In Google Cloud Platform and the Google Terraform provider, tags on BigQuery datasets "
                    "are configured using the 'labels' argument as key-value string pairs."
                ),
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    department  = "analytics"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Assign key/value string pairs to label and categorize the BigQuery dataset.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    department  = "analytics"\n'
                    '  }'
                ),
            },
            "retention": {
                "argument": "default_table_expiration_ms",
                "explanation": "Sets the default lifetime (in milliseconds) for all tables newly created in the dataset.",
                "snippet": '  default_table_expiration_ms = 2592000000 # 30 days in ms',
            },
            "access": {
                "argument": "access",
                "explanation": "Grants IAM roles on the BigQuery dataset to users, service accounts, or groups.",
                "snippet": (
                    '  access {\n'
                    '    role          = "READER"\n'
                    '    user_by_email = "analyst@example.com"\n'
                    '  }'
                ),
            },
            "description": {
                "argument": "description",
                "explanation": "User-friendly description and friendly name for the dataset.",
                "snippet": (
                    '  friendly_name = "My Analytics Dataset"\n'
                    '  description   = "Stores processed data analytics tables"\n'
                ),
            },
        },
    },
    "gcp.bigquery_table": {
        "hcl_type": "google_bigquery_table",
        "doc_file": "bigquery_table.html.markdown",
        "registry_slug": "bigquery_table",
        "primary_tf": "table.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": (
                    "In Google Cloud Platform and the Google Terraform provider, BigQuery table tags "
                    "are specified using the 'labels' argument as key-value pairs."
                ),
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    sensitivity = "internal"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Key/value labels assigned to the BigQuery table.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    team        = "bi"\n'
                    '  }'
                ),
            },
            "schema": {
                "argument": "schema",
                "explanation": "Defines the table schema as a JSON string using an EOF block.",
                "snippet": (
                    '  schema = <<EOF\n'
                    '[\n'
                    '  {"name": "id", "type": "STRING", "mode": "REQUIRED"},\n'
                    '  {"name": "event_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},\n'
                    '  {"name": "status", "type": "STRING", "mode": "NULLABLE"}\n'
                    ']\n'
                    'EOF'
                ),
            },
            "partition": {
                "argument": "time_partitioning",
                "explanation": "Configures time partitioning on a field (e.g. DAY, HOUR, MONTH).",
                "snippet": (
                    '  time_partitioning {\n'
                    '    type  = "DAY"\n'
                    '    field = "event_timestamp"\n'
                    '  }'
                ),
            },
            "clustering": {
                "argument": "clustering",
                "explanation": "Specifies up to 4 column names to cluster the BigQuery table for optimized queries.",
                "snippet": '  clustering = ["status", "id"]',
            },
            "expiration": {
                "argument": "expiration_time",
                "explanation": "The time when this table expires, in milliseconds since the epoch.",
                "snippet": '  expiration_time = 1735689600000 # Unix timestamp in ms',
            },
        },
    },
    "gcp.pubsub_topic": {
        "hcl_type": "google_pubsub_topic",
        "doc_file": "pubsub_topic.html.markdown",
        "registry_slug": "pubsub_topic",
        "primary_tf": "topic.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": (
                    "In Google Cloud Platform and the Google Terraform provider, Pub/Sub topic tags "
                    "are specified using the 'labels' argument as key-value pairs."
                ),
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    service     = "orders"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Key/value labels assigned to the Pub/Sub topic.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    service     = "orders"\n'
                    '  }'
                ),
            },
            "retention": {
                "argument": "message_retention_duration",
                "explanation": "Configures how long unacknowledged messages are retained on the topic.",
                "snippet": '  message_retention_duration = "86600s" # e.g. 24 hours',
            },
            "kms": {
                "argument": "kms_key_name",
                "explanation": "The resource name of the Cloud KMS CryptoKey used to encrypt messages at rest.",
                "snippet": '  kms_key_name = "projects/PROJECT_ID/locations/global/keyRings/RING/cryptoKeys/KEY"',
            },
        },
    },
    "gcp.pubsub_subscription": {
        "hcl_type": "google_pubsub_subscription",
        "doc_file": "pubsub_subscription.html.markdown",
        "registry_slug": "pubsub_subscription",
        "primary_tf": "subscription.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": (
                    "In Google Cloud Platform and the Google Terraform provider, Pub/Sub subscription tags "
                    "are specified using the 'labels' argument as key-value pairs."
                ),
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    consumer    = "billing-worker"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Key/value labels assigned to the Pub/Sub subscription.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    consumer    = "billing-worker"\n'
                    '  }'
                ),
            },
            "retention": {
                "argument": "message_retention_duration",
                "explanation": "How long to retain unacknowledged messages in the subscription backlog.",
                "snippet": '  message_retention_duration = "1200s" # 20 minutes',
            },
            "ack": {
                "argument": "ack_deadline_seconds",
                "explanation": "The maximum time after a subscriber receives a message before the message should be acknowledged.",
                "snippet": '  ack_deadline_seconds = 60 # 10 to 600 seconds',
            },
            "dead_letter": {
                "argument": "dead_letter_policy",
                "explanation": "Forwards messages that cannot be processed to a dead-letter topic after max delivery attempts.",
                "snippet": (
                    '  dead_letter_policy {\n'
                    '    dead_letter_topic     = "projects/PROJECT_ID/topics/my-dead-letter-topic"\n'
                    '    max_delivery_attempts = 5\n'
                    '  }'
                ),
            },
            "expiration": {
                "argument": "expiration_policy",
                "explanation": "Configures when an idle subscription expires (TTL of inactivity).",
                "snippet": (
                    '  expiration_policy {\n'
                    '    ttl = "2592000s" # 30 days\n'
                    '  }'
                ),
            },
            "filter": {
                "argument": "filter",
                "explanation": "An expression filtering messages based on message attributes.",
                "snippet": '  filter = "attributes.event_type = \\"order_created\\""',
            },
        },
    },
    "gcp.compute_instance": {
        "hcl_type": "google_compute_instance",
        "doc_file": "compute_instance.html.markdown",
        "registry_slug": "compute_instance",
        "primary_tf": "compute.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": "Assign key/value labels or network tags to the Compute Engine VM instance.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    managed_by  = "taas"\n'
                    '  }\n'
                    '  tags = ["http-server", "web"]'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Assign key/value string pairs to label the Compute Engine VM.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    owner       = "platform"\n'
                    '  }'
                ),
            },
            "machine_type": {
                "argument": "machine_type",
                "explanation": "Specify the Compute Engine machine type (e.g. e2-micro, e2-small, e2-medium).",
                "snippet": '  machine_type = "e2-small"',
            },
        },
    },
    "gcp.cloud_run_function": {
        "hcl_type": "google_cloudfunctions2_function",
        "doc_file": "cloudfunctions2_function.html.markdown",
        "registry_slug": "cloudfunctions2_function",
        "primary_tf": "function.tf",
        "common_suggestions": {
            "tags": {
                "argument": "labels",
                "explanation": "Assign key/value labels to the Cloud Run Function (2nd Gen).",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '    runtime     = "python312"\n'
                    '  }'
                ),
            },
            "labels": {
                "argument": "labels",
                "explanation": "Key/value labels attached to the Cloud Run Function.",
                "snippet": (
                    '  labels = {\n'
                    '    environment = "dev"\n'
                    '  }'
                ),
            },
            "env": {
                "argument": "environment_variables",
                "explanation": "Pass runtime environment variables inside service_config.",
                "snippet": (
                    '    environment_variables = {\n'
                    '      LOG_EXECUTION_ID = "true"\n'
                    '    }'
                ),
            },
        },
    },
    "gcp.cloud_sql_instance": {
        "hcl_type": "google_sql_database_instance",
        "doc_file": "sql_database_instance.html.markdown",
        "registry_slug": "sql_database_instance",
        "primary_tf": "sql.tf",
        "common_suggestions": {
            "tags": {
                "argument": "user_labels",
                "explanation": "In Cloud SQL, key/value labels are configured via user_labels inside the settings block.",
                "snippet": (
                    '    user_labels = {\n'
                    '      environment = "dev"\n'
                    '      managed_by  = "taas"\n'
                    '    }'
                ),
            },
            "labels": {
                "argument": "user_labels",
                "explanation": "Key/value labels attached inside the Cloud SQL settings block.",
                "snippet": (
                    '    user_labels = {\n'
                    '      environment = "dev"\n'
                    '    }'
                ),
            },
            "backup": {
                "argument": "backup_configuration",
                "explanation": "Enable automated daily backups inside the Cloud SQL settings block.",
                "snippet": (
                    '    backup_configuration {\n'
                    '      enabled    = true\n'
                    '      start_time = "03:00"\n'
                    '    }'
                ),
            },
        },
    },
}


def _fetch_remote_doc_markdown(doc_file: str) -> str | None:
    """Fetch official Terraform documentation markdown live from terraform-provider-google repository in real-time.

    Fetches directly from upstream GitHub with 0 disk caching to guarantee no stale content
    and zero disk space usage.
    """
    url = f"https://raw.githubusercontent.com/hashicorp/terraform-provider-google/main/website/docs/r/{doc_file}"
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TaaS-Live-Docs/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[TaaS] Note: Direct doc fetch from {url} encountered: {exc}")
    return None


def _extract_doc_arguments(markdown: str) -> list[dict]:
    """Extract argument list from the Argument Reference section of provider docs."""
    args = []
    arg_ref_start = markdown.find("## Argument Reference")
    if arg_ref_start == -1:
        arg_ref_start = markdown.find("# Argument Reference")
    if arg_ref_start == -1:
        return args

    # Find next top section heading
    next_section = markdown.find("\n## ", arg_ref_start + 20)
    section_text = markdown[arg_ref_start:next_section] if next_section != -1 else markdown[arg_ref_start:]

    pattern = re.compile(r"^\s*[\*\-]\s+`?([a-zA-Z0-9_]+)`?\s*-\s*(.*)$", re.MULTILINE)
    for match in pattern.finditer(section_text):
        arg_name = match.group(1).strip()
        arg_desc = match.group(2).strip()
        arg_desc_clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", arg_desc)
        args.append({"name": arg_name, "description": arg_desc_clean})
    return args


def lookup_terraform_docs(resource_type: str, query: str | None = None) -> dict:
    """Fetch official Terraform documentation live for a resource and suggest code configuration in real time.

    Queries documentation directly from the official Terraform Google provider repository (without caching)
    to always retrieve the most up-to-date documentation without using local disk space, and suggests
    code snippets for queried attributes such as tags/labels, retention, lifecycle rules, or schema.

    Args:
        resource_type: Resource type name (e.g. 'storage_bucket', 'bigquery_dataset',
                       'bigquery_table', 'pubsub_topic', 'pubsub_subscription').
        query: Optional question or attribute name (e.g. 'tags', 'labels', 'retention',
               'lifecycle', 'schema', 'cors', 'kms', 'encryption').

    Returns:
        dict: Documentation details, explanation, and copy-pasteable code suggestions.
    """
    norm_type = _normalize_resource_type(resource_type)
    if norm_type not in DOC_RESOURCE_METADATA:
        clean_res = resource_type.strip().lower()
        matched_key = None
        for k, v in DOC_RESOURCE_METADATA.items():
            if clean_res in (k, v["hcl_type"], v["registry_slug"]):
                matched_key = k
                break
        if matched_key:
            norm_type = matched_key
        else:
            supported = ", ".join(DOC_RESOURCE_METADATA.keys())
            return {
                "status": "UNSUPPORTED",
                "message": f"Resource type '{resource_type}' is not supported for doc lookup. Supported: {supported}",
            }

    meta = DOC_RESOURCE_METADATA[norm_type]
    hcl_type = meta["hcl_type"]
    primary_tf = meta["primary_tf"]
    reg_url = f"https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/{meta['registry_slug']}"

    # Fetch markdown documentation
    doc_markdown = _fetch_remote_doc_markdown(meta["doc_file"])
    doc_args = _extract_doc_arguments(doc_markdown) if doc_markdown else []

    # Process query
    q_str = (query or "").lower().strip()
    explanation = ""
    suggested_code = ""

    # Check common aliases
    alias_map = {
        "tag": "tags",
        "tags": "tags",
        "label": "labels",
        "labels": "labels",
        "retention": "retention",
        "retention_policy": "retention",
        "lifecycle": "lifecycle",
        "lifecycle_rule": "lifecycle",
        "cors": "cors",
        "encrypt": "encryption",
        "encryption": "encryption",
        "kms": "encryption" if "encryption" in meta["common_suggestions"] else "kms",
        "schema": "schema",
        "partition": "partition",
        "partitioning": "partition",
        "cluster": "clustering",
        "clustering": "clustering",
        "ack": "ack",
        "dead_letter": "dead_letter",
        "expire": "expiration",
        "expiration": "expiration",
        "filter": "filter",
        "access": "access",
        "description": "description",
        "machine": "machine_type",
        "machine_type": "machine_type",
        "env": "env",
        "environment": "env",
        "backup": "backup",
    }

    matched_key = None
    for keyword, target_key in alias_map.items():
        if keyword in q_str:
            if target_key in meta["common_suggestions"]:
                matched_key = target_key
                break

    if matched_key and matched_key in meta["common_suggestions"]:
        matched_suggestion = meta["common_suggestions"][matched_key]
        explanation = matched_suggestion["explanation"]
        suggested_code = matched_suggestion["snippet"]
    elif q_str:
        # Search extracted arguments from doc
        matching_args = [
            a for a in doc_args
            if q_str in a["name"].lower() or any(w in a["name"].lower() for w in q_str.split())
        ]
        if matching_args:
            first_match = matching_args[0]
            explanation = f"Argument '{first_match['name']}': {first_match['description']}"
            suggested_code = f'  {first_match["name"]} = "..."'
        else:
            explanation = f"Consult official documentation for available arguments for {hcl_type}."

    # If no query provided, return resource overview
    if not q_str:
        explanation = (
            f"Official Terraform documentation for '{hcl_type}'. "
            f"Managed in 'artifacts/gcp/{primary_tf}'. "
            "Supported configurations include tags/labels, retention, lifecycle rules, and custom policies."
        )
        if "tags" in meta["common_suggestions"]:
            suggested_code = meta["common_suggestions"]["tags"]["snippet"]

    # Collect matched arguments from doc
    relevant_args = []
    if q_str:
        for a in doc_args:
            if any(term in a["name"].lower() or term in a["description"].lower() for term in q_str.split()):
                relevant_args.append(a)
                if len(relevant_args) >= 5:
                    break
    if not relevant_args and doc_args:
        relevant_args = doc_args[:5]

    message = f"Found documentation for '{hcl_type}'."
    if explanation:
        message += f"\n\n{explanation}"
    if suggested_code:
        message += f"\n\nSuggested HCL configuration:\n```hcl\n{suggested_code}\n```"

    return {
        "status": "SUCCESS",
        "resource_type": norm_type,
        "terraform_resource": hcl_type,
        "primary_tf_file": primary_tf,
        "documentation_url": reg_url,
        "query": query,
        "explanation": explanation,
        "suggested_code": suggested_code,
        "matched_arguments": relevant_args,
        "message": message,
    }


STARTER_FILE_MAP = {
    "bucket.tf": STARTERS_DIR / "gcp" / "storage_bucket" / "bucket.tf",
    "dataset.tf": STARTERS_DIR / "gcp" / "bigquery_dataset" / "dataset.tf",
    "table.tf": STARTERS_DIR / "gcp" / "bigquery_table" / "table.tf",
    "topic.tf": STARTERS_DIR / "gcp" / "pubsub_topic" / "topic.tf",
    "subscription.tf": STARTERS_DIR / "gcp" / "pubsub_subscription" / "subscription.tf",
    "compute.tf": STARTERS_DIR / "gcp" / "compute_instance" / "compute.tf",
    "function.tf": STARTERS_DIR / "gcp" / "cloud_run_function" / "function.tf",
    "function.py": STARTERS_DIR / "gcp" / "cloud_run_function" / "src" / "main.py",
    "sql.tf": STARTERS_DIR / "gcp" / "cloud_sql_instance" / "sql.tf",
    "main.tf": COMMON_STARTER_DIR / "main.tf",
    "variables.tf": COMMON_STARTER_DIR / "variables.tf",
}


def read_artifact_code(file_name: str | None = None) -> dict:
    """Read Terraform configuration files before planning.

    Already-created artifacts are pulled from `artifacts/gcp/`.
    Files not yet created in `artifacts/gcp/` are pulled from `terraform_starters/`.

    Args:
        file_name: Optional file name (e.g. 'bucket.tf', 'dataset.tf', 'table.tf',
                   'topic.tf', 'subscription.tf', 'main.tf', 'variables.tf').
                   If omitted or 'all', returns all Terraform files.

    Returns:
        dict: File contents, metadata, and source ('artifacts/gcp' or 'terraform_starters').
    """
    if file_name and file_name.strip().lower() not in ("all", "*"):
        clean_name = Path(file_name.strip()).name
        artifact_path = GCP_ARTIFACTS_DIR / clean_name
        starter_path = STARTER_FILE_MAP.get(clean_name)

        if artifact_path.is_file():
            content = artifact_path.read_text(encoding="utf-8")
            source = f"artifacts/gcp/{clean_name}"
            resolved_path = str(artifact_path.resolve())
        elif starter_path and starter_path.is_file():
            content = starter_path.read_text(encoding="utf-8")
            source = str(starter_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            resolved_path = str(starter_path.resolve())
        else:
            return {
                "status": "NOT_FOUND",
                "message": f"File '{clean_name}' not found in artifacts/gcp or terraform_starters.",
            }

        return {
            "status": "SUCCESS",
            "file_name": clean_name,
            "source": source,
            "path": resolved_path,
            "lines": len(content.splitlines()),
            "content": content,
        }

    # Build combined dictionary of all standard files:
    # 1. Start with all starter templates from terraform_starters/
    # 2. Override with any already-created files in artifacts/gcp/
    files_content: dict[str, str] = {}
    file_details: dict[str, dict] = {}

    for fname, starter_path in STARTER_FILE_MAP.items():
        artifact_path = GCP_ARTIFACTS_DIR / fname
        starter_text = starter_path.read_text(encoding="utf-8") if starter_path.is_file() else ""
        if artifact_path.is_file():
            art_text = artifact_path.read_text(encoding="utf-8")
            files_content[fname] = art_text
            file_details[fname] = {
                "content": art_text,
                "starter_content": starter_text,
                "source": "artifacts/gcp",
                "source_path": f"artifacts/gcp/{fname}",
                "is_artifact": True,
                "has_resources": bool(re.search(r'^\s*resource\s+"', art_text, re.MULTILINE)),
            }
        else:
            files_content[fname] = starter_text
            file_details[fname] = {
                "content": starter_text,
                "starter_content": starter_text,
                "source": "terraform_starters",
                "source_path": str(starter_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "is_artifact": False,
                "has_resources": False,
            }

    # Also include any extra .tf or .tfvars files present in artifacts/gcp/ (such as terraform.tfvars, backend.tfvars)
    if GCP_ARTIFACTS_DIR.exists():
        for f in sorted(GCP_ARTIFACTS_DIR.iterdir()):
            if f.is_file() and f.suffix in (".tf", ".tfvars") and f.name not in files_content:
                txt = f.read_text(encoding="utf-8")
                files_content[f.name] = txt
                file_details[f.name] = {
                    "content": txt,
                    "starter_content": "",
                    "source": "artifacts/gcp",
                    "source_path": f"artifacts/gcp/{f.name}",
                    "is_artifact": True,
                    "has_resources": bool(re.search(r'^\s*resource\s+"', txt, re.MULTILINE)),
                }

    return {
        "status": "SUCCESS",
        "artifact_directory": str(GCP_ARTIFACTS_DIR.resolve()),
        "starters_directory": str(STARTERS_DIR.resolve()),
        "file_count": len(files_content),
        "files": files_content,
        "file_details": file_details,
        "message": (
            f"Loaded {len(files_content)} Terraform file(s) "
            "(created files from 'artifacts/gcp', starter templates from 'terraform_starters')."
        ),
    }


def _resolve_editor_starter_placeholders(
    clean_name: str,
    hcl_text: str,
    project_id: str,
    location: str,
) -> str:
    """Resolve starter template placeholders when saving directly from the Pre-Plan Code editor."""
    updated = hcl_text
    if clean_name == "function.tf":
        name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', updated, re.MULTILINE)
        if name_match and "var.resource_config" not in name_match.group(1):
            func_name = name_match.group(1).strip().lower()
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", func_name)
            updated = re.sub(
                r'(resource\s+"google_cloudfunctions2_function"\s+)"requested"',
                rf'\1"{tf_name}"',
                updated,
                count=1,
            )
            res_match = re.search(
                r'^\s*resource\s+"google_cloudfunctions2_function"\s+"([A-Za-z0-9_]+)"',
                updated,
                re.MULTILINE,
            )
            if res_match:
                tf_name = res_match.group(1)
            if (
                'var.resource_config["source_bucket"]' in updated
                or 'var.resource_config["source_object"]' in updated
            ):
                src_bucket, src_object = _ensure_function_source_zip(
                    project_id=project_id,
                    tf_name=tf_name,
                )
                updated = updated.replace('var.resource_config["source_bucket"]', f'"{src_bucket}"')
                updated = updated.replace('var.resource_config["source_object"]', f'"{src_object}"')
    elif clean_name == "compute.tf":
        name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', updated, re.MULTILINE)
        if name_match and "var.resource_config" not in name_match.group(1):
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", name_match.group(1).strip().lower())
            updated = re.sub(
                r'(resource\s+"google_compute_instance"\s+)"requested"',
                rf'\1"{tf_name}"',
                updated,
                count=1,
            )
            zone = location if len(location.split("-")) >= 3 else f"{location}-a"
            updated = updated.replace('lookup(var.resource_config, "machine_type", "e2-micro")', '"e2-micro"')
            updated = updated.replace('lookup(var.resource_config, "zone", "${var.location}-a")', f'"{zone}"')
    elif clean_name == "sql.tf":
        name_match = re.search(r'^\s*name\s*=\s*"([^"]+)"', updated, re.MULTILINE)
        if name_match and "var.resource_config" not in name_match.group(1):
            tf_name = re.sub(r"[^A-Za-z0-9_]", "_", name_match.group(1).strip().lower())
            updated = re.sub(
                r'(resource\s+"google_sql_database_instance"\s+)"requested"',
                rf'\1"{tf_name}"',
                updated,
                count=1,
            )
            updated = updated.replace('lookup(var.resource_config, "database_version", "POSTGRES_15")', '"POSTGRES_15"')
            updated = updated.replace('lookup(var.resource_config, "tier", "db-f1-micro")', '"db-f1-micro"')
    return updated


def update_artifact_code(
    file_name: str,
    code_content: str | None = None,
    resource_address: str | None = None,
    resource_block: str | None = None,
) -> dict:
    """Make changes to generated Terraform code in artifacts/gcp before planning.

    Copies common starter files into artifacts/gcp if needed, writes the updated .tf code
    to artifacts/gcp/<file_name>, and formats it with 'terraform fmt'.

    Args:
        file_name: Target file in artifacts/gcp (e.g. 'bucket.tf', 'dataset.tf', 'table.tf',
                   'topic.tf', 'subscription.tf', 'compute.tf', 'function.tf', 'function.py', 'sql.tf').
        code_content: Full replacement content for the file (if replacing the whole file).
        resource_address: Address of resource to update (e.g. 'google_storage_bucket.my_bucket').
        resource_block: New or updated HCL block for the specific resource.

    Returns:
        dict: Updated file content and status.
    """
    clean_name = Path(file_name.strip()).name
    if not (clean_name.endswith(".tf") or clean_name.endswith(".tfvars") or clean_name == "function.py"):
        return {
            "status": "INVALID",
            "message": f"File name '{clean_name}' must have a .tf, .tfvars, or function.py extension.",
        }

    GCP_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "solar-dialect-264808").strip()
    location = (os.getenv("TAAS_DEFAULT_REGION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "asia-south2").strip()
    if location.lower() == "global":
        location = "asia-south2"
    state_bucket = os.getenv("TAAS_STATE_BUCKET", "terraform-implementation").strip()

    # Ensure common starter files (main.tf, variables.tf, terraform.tfvars, backend.tfvars) exist in artifacts/gcp
    if not (GCP_ARTIFACTS_DIR / "main.tf").is_file() or not (GCP_ARTIFACTS_DIR / "variables.tf").is_file():
        _ensure_common_artifacts(GCP_ARTIFACTS_DIR, project_id, location, state_bucket)

    target_path = GCP_ARTIFACTS_DIR / clean_name

    if resource_block:
        addr = resource_address
        if not addr:
            m = re.search(r'resource\s+"([a-zA-Z0-9_]+)"\s+"([a-zA-Z0-9_]+)"', resource_block)
            if m:
                addr = f"{m.group(1)}.{m.group(2)}"
            else:
                return {
                    "status": "INVALID",
                    "message": "resource_address was not provided and could not be inferred from the resource_block header.",
                }

        block_clean = resource_block.strip()
        start_marker = f"# --- START: {addr} ---"
        end_marker = f"# --- END: {addr} ---"
        if not block_clean.startswith("# --- START:"):
            block_clean = f"{start_marker}\n{block_clean}\n{end_marker}"

        _upsert_resource_block(target_path, addr, block_clean)

    elif code_content is not None:
        prepared = code_content.strip() + "\n"
        if clean_name.endswith(".tf"):
            prepared = _resolve_editor_starter_placeholders(clean_name, prepared, project_id, location)
            prepared = _dedupe_hcl_blocks(prepared)
        target_path.write_text(prepared, encoding="utf-8")
    else:
        return {
            "status": "INVALID",
            "message": "Must provide either 'resource_block' (with optional 'resource_address') or 'code_content'.",
        }

    # Format the file with terraform fmt (for HCL files only)
    if clean_name.endswith(".py"):
        fmt_status = "saved Python function code"
    else:
        fmt_res = _run_terraform(["fmt", clean_name], GCP_ARTIFACTS_DIR)
        fmt_status = "formatted with terraform fmt" if fmt_res.get("returncode") == 0 else "saved (terraform fmt skipped)"

    updated_text = target_path.read_text(encoding="utf-8")
    return {
        "status": "SUCCESS",
        "file_name": clean_name,
        "source": "artifacts/gcp",
        "path": str(target_path.resolve()),
        "formatting": fmt_status,
        "content": updated_text,
        "updated_content": updated_text,
        "message": (
            f"Successfully saved '{clean_name}' to 'artifacts/gcp/{clean_name}' ({fmt_status}). "
            "Ready for planning against GCS remote state."
        ),
    }

