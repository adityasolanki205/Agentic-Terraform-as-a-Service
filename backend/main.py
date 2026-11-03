"""Unified FastAPI Backend Server.

Serves all three services under a single gateway:
1. Terraform-as-a-Service (/api/taas/*) — Cloud Infrastructure Studio, Starter + Artifact Code Editor, GCS State
2. Agentic DataOps (/api/dataops/*) — ServiceNow Incident Analytics on BigQuery (Basic view)
3. EnterpriseGPT (/api/enterprise/*) — HR & Employee Corporate Assistant (Basic view)
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Literal, Optional
from uuid import uuid4
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

# Preserve regional setting for Terraform GCP resources (default asia-south2),
# while ensuring Vertex AI Gemini API always routes through the 'global' endpoint
# (calling Vertex AI Gemini in asia-south2 returns 501 UNIMPLEMENTED).
_configured_loc = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south2").strip()
if _configured_loc and _configured_loc.lower() != "global":
    os.environ.setdefault("TAAS_DEFAULT_REGION", _configured_loc)
os.environ["GOOGLE_CLOUD_LOCATION"] = os.getenv("VERTEX_AI_LOCATION", "global")

if not os.getenv("GEMINI_API_KEY"):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

from taas_agent.tools.tools import (
    GCP_ARTIFACTS_DIR,
    REQUESTS_DIR,
    SUPPORTED_RESOURCES,
    _now,
    _save_record,
    apply_resource,
    generate_resource_files,
    get_request_status,
    list_taas_resources,
    lookup_terraform_docs,
    plan_deactivate_resource,
    plan_recreate_resource,
    plan_resource,
    read_artifact_code,
    update_artifact_code,
    verify_resource,
)
from dataops_agent.agent import chat_with_dataops_agent
from dataops_agent.tools import get_dataops_dashboard_kpis
from enterprise_gpt.service import handle_enterprise_chat, process_uploaded_documents

app = FastAPI(
    title="Terraform-as-a-Service & Unified Agentic AI Platform",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Request / Response Models
# ==============================================================================


class DataOpsChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class EnterpriseChatJsonRequest(BaseModel):
    query: str
    role: str = "employee"


class TaaSChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ArtifactUpdateRequest(BaseModel):
    file_name: str
    code_content: Optional[str] = None
    resource_address: Optional[str] = None
    resource_block: Optional[str] = None


class PlanRequest(BaseModel):
    request_id: Optional[str] = None
    file_name: Optional[str] = None


class ApprovePlanRequest(BaseModel):
    decision: Literal["apply", "dont apply"] = "apply"
    plan_id: Optional[str] = None
    request_id: Optional[str] = None
    plan_sha256: Optional[str] = None


class ResourceLifecycleRequest(BaseModel):
    project_id: Optional[str] = None
    resource_name: str
    resource_type: Optional[str] = None
    resource_category: Optional[str] = None
    dataset_id: Optional[str] = None


class DocLookupRequest(BaseModel):
    resource_type: str
    query: Optional[str] = None


# ==============================================================================
# Health Check
# ==============================================================================


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "services": [
            "Terraform-as-a-Service (GCP Infrastructure Studio)",
            "Agentic DataOps (ServiceNow Incident Analytics)",
            "EnterpriseGPT (HR & Employee Portals)",
        ],
    }


# ==============================================================================
# 1. EnterpriseGPT Basic Endpoints
# ==============================================================================


@app.post("/api/enterprise/chat")
async def enterprise_chat_json(req: EnterpriseChatJsonRequest):
    try:
        return await handle_enterprise_chat(message=req.query, portal=req.role)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/enterprise/process-documents")
async def enterprise_upload(files: List[UploadFile] = File(...)):
    try:
        return await process_uploaded_documents(files)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ==============================================================================
# 2. Agentic DataOps Basic Endpoints
# ==============================================================================


@app.get("/api/dataops/kpis")
def dataops_kpis():
    return get_dataops_dashboard_kpis()


@app.post("/api/dataops/chat")
def dataops_chat(req: DataOpsChatRequest):
    try:
        return chat_with_dataops_agent(message=req.message, session_id=req.session_id)
    except Exception as exc:
        return {
            "status": "ERROR",
            "response": f"Error communicating with Agentic DataOps: {exc}",
        }


# ==============================================================================
# 3. Terraform-as-a-Service (TaaS) Studio Endpoints
# ==============================================================================

TAAS_CHAT_SYSTEM_INSTRUCTION = """
You are the Terraform-as-a-Service (TaaS) Cloud Infrastructure Assistant.
Help developers provision, customize, plan, deactivate, and recreate Google Cloud resources.

Supported resources (starter templates in `terraform_starters/`, created artifacts in `artifacts/gcp/`, single remote state in GCS bucket):
- Google Cloud BigQuery dataset (`gcp.bigquery_dataset`): `dataset.tf`
- Google Cloud BigQuery table (`gcp.bigquery_table`): `table.tf` (pass `config={"dataset_id": dataset_id, "schema": schema_json}`)
- Google Cloud Storage bucket (`gcp.storage_bucket`): `bucket.tf`
- Google Cloud Pub/Sub topic (`gcp.pubsub_topic`): `topic.tf`
- Google Cloud Pub/Sub subscription (`gcp.pubsub_subscription`): `subscription.tf` (pass `config={"topic": topic_name}`)

WORKFLOW:
1. CREATE & PRE-PLAN CUSTOMIZATION:
   - Collect required parameters (default project_id is `solar-dialect-264808` and default location is `asia-south2` unless specified otherwise).
   - For BigQuery tables, ask if the user wants to provide a JSON schema or create without a schema.
   - Call `generate_resource_files` to pull from `terraform_starters/` and write the resource block into `artifacts/gcp/<file>.tf`.
   - Present the generated HCL code in a ```hcl block and tell the user:
     "Here is the generated Terraform code in `artifacts/gcp/`. You can review or edit it directly in the **Pre-Plan Code Editor** on the right, ask me how to add attributes (like tags/labels, retention, or lifecycle rules), or click **Run `terraform plan`** when ready."
   - When asked how to configure an attribute (e.g. "how to add tags/labels or lifecycle rules"), call `lookup_terraform_docs` (fetches live docs with zero cache) and suggest the HCL snippet.
   - When asked to modify code via chat, call `update_artifact_code`.
   - When the user says "proceed to plan" or "run plan", call `plan_resource(request_id)`.
   - After `plan_resource` returns `AWAITING_APPROVAL`, show the plan summary and instruct the user to use the **Approval Gate (`apply` / `dont apply`)** to confirm or cancel.
2. DELETE / DEACTIVATE:
   - Call `plan_deactivate_resource` to comment out (`#`) the resource block in `artifacts/gcp/` and generate a destroy plan.
3. RECREATE:
   - Call `plan_recreate_resource` to uncomment the resource block and generate a creation plan.
4. LIST / STATUS:
   - Use `list_taas_resources` and `get_request_status`.
"""

TAAS_SAFE_CHAT_TOOLS = [
    generate_resource_files,
    read_artifact_code,
    update_artifact_code,
    lookup_terraform_docs,
    plan_resource,
    plan_deactivate_resource,
    plan_recreate_resource,
    get_request_status,
    list_taas_resources,
]

_TAAS_SESSIONS: dict[str, object] = {}


def _get_latest_request_info() -> dict:
    """Inspect `.taas/requests` for the most recently updated request record."""
    import json

    if not REQUESTS_DIR.exists():
        return {}
    records = []
    for item in REQUESTS_DIR.iterdir():
        rec_file = item / "request.json"
        if rec_file.is_file():
            try:
                records.append(json.loads(rec_file.read_text(encoding="utf-8")))
            except Exception:
                continue
    if not records:
        return {}
    records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    latest = records[0]
    primary_tf = Path(latest.get("primary_tf_file", "")).name if latest.get("primary_tf_file") else None
    pending_plan = None
    if latest.get("status") == "AWAITING_APPROVAL":
        pending_plan = {
            "plan_id": latest["request_id"],
            "request_id": latest["request_id"],
            "plan_sha256": latest.get("plan_sha256", ""),
            "status": "AWAITING_APPROVAL",
            "action": latest.get("action", "CREATE"),
            "resource_type": latest.get("resource_type"),
            "resource_name": latest.get("resource_name"),
            "project_id": latest.get("project_id"),
            "plan_summary": (
                f"{latest.get('action', 'CREATE')} {latest.get('resource_type')} "
                f"'{latest.get('resource_name')}' in {latest.get('project_id')}"
            ),
            "plan_output": (latest.get("plan_summary") or "")[:15000],
        }
    return {
        "latest_request_id": latest.get("request_id"),
        "latest_status": latest.get("status"),
        "active_file": primary_tf,
        "pending_plan": pending_plan,
        "pending_approval": pending_plan,
    }


def _ensure_request_record_for_file(file_name: str) -> Optional[str]:
    """If a user edited a .tf file directly in the editor and clicked Run Plan,
    ensure there is a valid request record in `.taas/requests` for the resource in that file."""
    info = _get_latest_request_info()
    if info.get("latest_request_id"):
        return info["latest_request_id"]

    file_to_rtype = {
        "bucket.tf": "gcp.storage_bucket",
        "dataset.tf": "gcp.bigquery_dataset",
        "table.tf": "gcp.bigquery_table",
        "topic.tf": "gcp.pubsub_topic",
        "subscription.tf": "gcp.pubsub_subscription",
    }
    rtype = file_to_rtype.get(file_name)
    if not rtype:
        return None

    tf_path = GCP_ARTIFACTS_DIR / file_name
    if not tf_path.is_file():
        return None

    text = tf_path.read_text(encoding="utf-8")
    matches = list(re.finditer(r'^\s*resource\s+"([a-zA-Z0-9_]+)"\s+"([a-zA-Z0-9_]+)"', text, re.MULTILINE))
    if not matches:
        return None

    last_match = matches[-1]
    hcl_type, tf_name = last_match.group(1), last_match.group(2)
    expected_address = f"{hcl_type}.{tf_name}"

    # Extract cloud name from block if possible
    name_match = re.search(r'(?:name|dataset_id|table_id)\s*=\s*"([^"]+)"', text[last_match.start():])
    cloud_name = name_match.group(1) if name_match else tf_name

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "solar-dialect-264808").strip()
    location = os.getenv("TAAS_DEFAULT_REGION", "asia-south2").strip()
    request_id = str(uuid4())

    record = {
        "request_id": request_id,
        "action": "CREATE",
        "resource_type": rtype,
        "resource_name": cloud_name,
        "project_id": project_id,
        "location": location,
        "resource_config": {},
        "artifact_directory": str(GCP_ARTIFACTS_DIR.resolve()),
        "primary_tf_file": str(tf_path.resolve()),
        "expected_address": expected_address,
        "tf_resource_name": tf_name,
        "status": "ARTIFACTS_READY",
        "status_message": f"Resource block '{expected_address}' ready for planning in {file_name}.",
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save_record(record)
    return request_id


@app.post("/api/taas/chat")
def taas_chat(req: TaaSChatRequest):
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        project = (
            os.getenv("GOOGLE_CLOUD_PROJECT")
            or os.getenv("PROJECT_ID")
            or "solar-dialect-264808"
        )
        preferred_model = os.getenv("TAAS_MODEL", "gemini-3.5-flash-lite")

        chat_config = types.GenerateContentConfig(
            system_instruction=TAAS_CHAT_SYSTEM_INSTRUCTION,
            tools=TAAS_SAFE_CHAT_TOOLS,
            temperature=0.1,
        )

        # Vertex AI Gemini models (especially gemini-3.5-flash-lite & gemini-2.5-flash)
        # require 'global' or 'us-central1' (regional endpoints like asia-south2 return 501 UNIMPLEMENTED).
        candidates = [
            ("global", preferred_model),
            ("global", "gemini-2.5-flash"),
            ("us-central1", "gemini-2.5-flash"),
            ("global", "gemini-2.0-flash"),
            ("us-central1", "gemini-2.0-flash"),
        ]

        response = None
        last_err = None

        if req.session_id in _TAAS_SESSIONS:
            try:
                response = _TAAS_SESSIONS[req.session_id].send_message(req.message)
            except Exception as session_err:
                last_err = session_err
                _TAAS_SESSIONS.pop(req.session_id, None)

        if response is None:
            for loc, mdl in candidates:
                try:
                    if api_key:
                        client = genai.Client(api_key=api_key)
                    else:
                        client = genai.Client(vertexai=True, project=project, location=loc)
                    chat_session = client.chats.create(model=mdl, config=chat_config)
                    response = chat_session.send_message(req.message)
                    _TAAS_SESSIONS[req.session_id] = chat_session
                    break
                except Exception as attempt_err:
                    last_err = attempt_err
                    continue

        if response is None:
            raise last_err or RuntimeError("All Gemini model endpoints failed.")

        artifacts_data = read_artifact_code()
        req_info = _get_latest_request_info()

        return {
            "status": "SUCCESS",
            "response": response.text or "Operation completed.",
            "files": artifacts_data.get("file_details", {}),
            "raw_files": artifacts_data.get("files", {}),
            **req_info,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "response": f"⚠️ Error in TaaS Agent: {exc}",
        }


@app.get("/api/taas/artifacts")
def get_artifacts(file_name: Optional[str] = None):
    res = read_artifact_code(file_name=file_name)
    req_info = _get_latest_request_info()
    return {
        **res,
        "files": res.get("file_details", {}),
        "raw_files": res.get("files", {}),
        **req_info,
    }


@app.post("/api/taas/artifacts/update")
@app.put("/api/taas/artifacts")
def save_artifact(req: ArtifactUpdateRequest):
    res = update_artifact_code(
        file_name=req.file_name,
        code_content=req.code_content,
        resource_address=req.resource_address,
        resource_block=req.resource_block,
    )
    all_data = read_artifact_code()
    req_info = _get_latest_request_info()
    return {
        **res,
        "files": all_data.get("file_details", {}),
        "raw_files": all_data.get("files", {}),
        **req_info,
    }


@app.post("/api/taas/plan")
def trigger_plan(req: Optional[PlanRequest] = None):
    request_id = req.request_id if req and req.request_id else None
    file_name = req.file_name if req and req.file_name else "bucket.tf"
    if not request_id:
        request_id = _ensure_request_record_for_file(file_name)
    if not request_id:
        return {
            "status": "ERROR",
            "message": (
                "No generated resource request found to plan. "
                "Generate a resource via chat/1-Click TaaS or save a valid resource block in the editor first."
            ),
        }

    res = plan_resource(request_id=request_id)
    req_info = _get_latest_request_info()
    return {
        **res,
        "plan_id": request_id,
        "plan_output": res.get("plan_summary", ""),
        "details": res.get("message", ""),
        **req_info,
    }


@app.post("/api/taas/approve")
@app.post("/api/taas/apply")
async def trigger_apply(req: ApprovePlanRequest):
    info = _get_latest_request_info()
    pending = info.get("pending_plan") or {}
    request_id = req.request_id or req.plan_id or pending.get("request_id") or info.get("latest_request_id")
    plan_sha256 = req.plan_sha256 or pending.get("plan_sha256", "")

    if not request_id:
        return {"status": "ERROR", "message": "No pending plan found to approve."}

    apply_res = apply_resource(
        request_id=request_id,
        plan_sha256=plan_sha256,
        confirmation=req.decision,
    )
    if req.decision == "dont apply":
        return {
            "status": "CANCELLED",
            "plan_id": request_id,
            "message": apply_res.get("message", "Plan cancelled."),
        }

    if apply_res.get("status") not in ("APPLIED", "DEACTIVATED"):
        return {
            "status": apply_res.get("status", "ERROR"),
            "plan_id": request_id,
            "message": apply_res.get("message", "Terraform apply failed."),
            "details": apply_res.get("apply_summary", ""),
        }

    verify_res = await verify_resource(request_id=request_id)
    return {
        "status": "SUCCESS",
        "plan_id": request_id,
        "request_id": request_id,
        "apply_output": apply_res.get("apply_summary", ""),
        "verify_result": verify_res,
        "message": verify_res.get("message") or apply_res.get("message"),
    }


@app.get("/api/taas/resources")
def get_resources(project_id: Optional[str] = None):
    raw = list_taas_resources(project_id=project_id, include_deactivated=True)
    items = raw.get("resources", [])
    active_by_cat: dict[str, list] = {
        "storage_bucket": [],
        "bigquery_dataset": [],
        "bigquery_table": [],
        "pubsub_topic": [],
        "pubsub_subscription": [],
    }
    deactivated_by_cat: dict[str, list] = {
        "storage_bucket": [],
        "bigquery_dataset": [],
        "bigquery_table": [],
        "pubsub_topic": [],
        "pubsub_subscription": [],
    }
    active_count = 0

    for item in items:
        rtype = item.get("resource_type", "")
        short_cat = rtype.replace("gcp.", "")
        entry = {
            "project_id": item.get("project_id"),
            "resource_type": rtype,
            "cloud_name": item.get("resource_name"),
            "tf_name": item.get("resource_name"),
            "dataset_id": item.get("dataset_id"),
            "address": f"{rtype} ({item.get('resource_name')})",
            "status": item.get("status"),
            "deactivated_at": item.get("last_updated"),
        }
        if item.get("status") in ("READY", "APPLIED"):
            active_by_cat.setdefault(short_cat, []).append(entry)
            active_count += 1
        else:
            deactivated_by_cat.setdefault(short_cat, []).append(entry)

    return {
        "status": "SUCCESS",
        "active": active_by_cat,
        "deactivated": deactivated_by_cat,
        "active_count": active_count,
        "raw_resources": items,
    }


@app.post("/api/taas/resources/deactivate")
@app.post("/api/taas/deactivate")
def trigger_deactivate(req: ResourceLifecycleRequest):
    project_id = req.project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "solar-dialect-264808")
    rtype = req.resource_type or (f"gcp.{req.resource_category}" if req.resource_category else "gcp.storage_bucket")
    res = plan_deactivate_resource(
        project_id=project_id,
        resource_name=req.resource_name,
        resource_type=rtype,
        dataset_id=req.dataset_id,
    )
    artifacts_data = read_artifact_code()
    req_info = _get_latest_request_info()
    return {
        **res,
        "files": artifacts_data.get("file_details", {}),
        **req_info,
    }


@app.post("/api/taas/resources/reactivate")
@app.post("/api/taas/recreate")
def trigger_recreate(req: ResourceLifecycleRequest):
    project_id = req.project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "solar-dialect-264808")
    rtype = req.resource_type or (f"gcp.{req.resource_category}" if req.resource_category else "gcp.storage_bucket")
    res = plan_recreate_resource(
        project_id=project_id,
        resource_name=req.resource_name,
        resource_type=rtype,
        dataset_id=req.dataset_id,
    )
    artifacts_data = read_artifact_code()
    req_info = _get_latest_request_info()
    return {
        **res,
        "files": artifacts_data.get("file_details", {}),
        **req_info,
    }


@app.post("/api/taas/docs")
def search_docs(req: DocLookupRequest):
    res = lookup_terraform_docs(resource_type=req.resource_type, query=req.query)
    return {
        **res,
        "registry_url": res.get("documentation_url"),
        "suggested_hcl_snippet": res.get("suggested_code"),
        "matched_argument_documentation": [
            f"**`{a['name']}`**: {a['description']}" for a in res.get("matched_arguments", [])
        ],
    }


# Serve React static build if available
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
