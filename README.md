# Agentic Terraform as a Service (TaaS) & Unified Enterprise AI Studio

A unified, declarative **Terraform-as-a-Service (TaaS)** platform and multi-service enterprise AI workspace powered by **Google ADK**, **Vertex AI Gemini**, **FastAPI**, and **React (Vite)**.

It brings three services together under a single web application with role-based access control:
1. **Terraform-as-a-Service (TaaS Studio)** — Full-featured interactive cloud infrastructure studio for provisioning, customizing, planning, deactivating, and recreating Google Cloud resources (`BigQuery Datasets`, `BigQuery Tables`, `Cloud Storage Buckets`, `Pub/Sub Topics`, and `Pub/Sub Subscriptions`).
2. **Agentic DataOps** — ServiceNow ITSM Incident Analytics powered by Google BigQuery (`solar-dialect-264808.servicenow_itsm.incidents`) for MTTR, backlog aging, and opened/closed ticket metrics.
3. **EnterpriseGPT** — Corporate HR & Employee assistant backed by BigQuery (`employee_data`), ChromaDB Vector Search, and Google Cloud Storage for bench analytics, candidate resume search, and policy Q&A.

---

## Key Features of TaaS Studio

1. **Crisp White Enterprise UI with Antigravity-Style Draggable Workbench**:
   - **Left Sidebar**: `+ New chat` button, persistent **Chats & History** list, and **1-Click TaaS** quick-action buttons.
   - **Rounded Service Switcher Dropdown**: Seamlessly switch between **Terraform-as-a-Service (TaaS Studio)** and **Agentic DataOps** from a single rounded pill dropdown.
   - **Cursor-Draggable & Minimizable Right Sidecar Panel**: Drag the vertical splitter bar left or right with your cursor (`26%` to `76%` width, double-click to reset to `54%`), or click the **Minimize** button to collapse the panel into a slim `48px` vertical dock rail.
   - **Floating Spheres Thinking Indicator**: Displays animated floating spheres (`• • •`) while the agent processes requests.
2. **Pre-Plan Code Editor (`terraform_starters/` + `artifacts/gcp/`)**:
   - **Never Blank**: Automatically pulls approved starter templates from `terraform_starters/` when a resource file has not yet been generated, and pulls active files from `artifacts/gcp/` once created.
   - **Live Editing & Formatting**: Edit `bucket.tf`, `dataset.tf`, `table.tf`, `topic.tf`, `subscription.tf`, `main.tf`, or `variables.tf` directly in the browser or via chat. Saving writes back to `artifacts/gcp/` in Cloud Shell and runs `terraform fmt`.
3. **Live Terraform Documentation Lookup (Zero Disk Cache)**:
   - Fetches official HashiCorp Google Provider documentation live on demand (`labels`, `lifecycle_rule`, `retention_policy`, `schema`, etc.) and allows 1-click insertion of HCL snippets into the Pre-Plan editor.
4. **AST-Validated Terraform Plan & Mandatory Approval Gate**:
   - Initializes the remote GCS state backend (`gs://<TAAS_STATE_BUCKET>/taas/<project_id>/gcp`) and runs `terraform plan`.
   - Verifies that *only* the requested resource address is modified before presenting the **Approval Gate** (`apply` / `dont apply`).
5. **Cloud Inventory Showcase, Deactivation & 1-Click Recreation**:
   - **Active Resources Panel**: Displays live KPI cards (`Active in GCP`, `Deactivated`, `Primary Region`), filter pills (`All`, `Active`, `Deactivated`), and live search.
   - **Safe Deactivation**: Commenting out (`#`) only the target resource block in `artifacts/gcp/<file>.tf` and applying destroy removes the cloud resource and updates GCS state while preserving the HCL block for 1-click **Recreate**.

---

## Role-Based Login Credentials

| Role | Username | Password | Accessible Services |
| :--- | :--- | :--- | :--- |
| **Cloud Developer** | `dev` | `dev` | **Terraform-as-a-Service (TaaS Studio)** & **Agentic DataOps** (via top dropdown) |
| **HR Administrator** | `admin` | `admin` | **EnterpriseGPT (HR Portal)** — Bench SQL + Resume & Policy RAG |
| **Enterprise Employee** | `user` | `user` | **EnterpriseGPT (Employee Portal)** — Corporate Policy Assistant |

---

## Project Layout

```text
backend/
  main.py                              # Unified FastAPI Gateway (/api/taas/*, /api/dataops/*, /api/enterprise/*)
frontend/
  vite.config.js                       # Vite server (port 8080) proxying /api -> http://localhost:8000
  src/
    main.jsx                           # React entrypoint
    StudioApp.jsx                      # Unified White-Theme TaaS Studio + Draggable Sidecar + DataOps + EnterpriseGPT
    StudioLight.css                    # Crisp White / Enterprise Gemini stylesheet & Antigravity splitter styles
taas_agent/
  agent.py                             # ADK Agent (TaaSAgent, approval gates)
  skills/terraform-provisioning/SKILL.md # Provisioning & deactivation guidance
  tools/
    tools.py                           # Deterministic lifecycle tools (generate, read/update code, docs, plan, apply, deactivate, recreate, verify)
dataops_agent/
  agent.py                             # ADK Multi-Agent Supervisor for ServiceNow Incident Analytics
  tools.py                             # BigQuery analytics tools (MTTR, aging, opened/closed counts)
enterprise_gpt/
  service.py                           # EnterpriseGPT service (BigQuery bench SQL, ChromaDB RAG, GCS uploads)
terraform_starters/                    # Approved Terraform templates (source of truth)
  common/
    main.tf                            # GCS backend & Google provider starter
    variables.tf                       # Shared variables starter
  gcp/
    bigquery_dataset/dataset.tf        # Dataset resource starter template
    bigquery_table/table.tf            # Table resource starter template
    storage_bucket/bucket.tf           # GCS bucket starter template
    pubsub_topic/topic.tf              # Pub/Sub topic starter template
    pubsub_subscription/subscription.tf # Pub/Sub subscription starter template
artifacts/                             # Created at runtime from starters
  gcp/                                 # Single runtime folder for all GCP resources
    main.tf                            # Copied at runtime from common/main.tf
    variables.tf                       # Copied at runtime from common/variables.tf
    dataset.tf                         # All BigQuery datasets (commented when deactivated)
    table.tf                           # All BigQuery tables (commented when deactivated)
    bucket.tf                          # All GCS buckets (commented when deactivated)
    topic.tf                           # All Pub/Sub topics (commented when deactivated)
    subscription.tf                    # All Pub/Sub subscriptions (commented when deactivated)
    backend.tfvars                     # GCS state config (taas/<project_id>/gcp)
    terraform.tfvars                   # Runtime project & location vars
.taas/requests/                        # Local request records, metadata, and saved plans
```

---

## Quick Start in Google Cloud Shell

### 1. One-Click Environment & Terraform Setup
Run `setup.sh` once to install persistent Terraform v1.9.8 (`~/.local/bin/terraform`), create the Python virtual environment, install dependencies, and generate `.env`:

```bash
cd ~/Agentic-Terraform-as-a-Service
bash setup.sh
```

### 2. Run the Unified Web Platform (Backend + Frontend)

Open **two terminal tabs** in Google Cloud Shell:

#### Terminal 1 — Start the FastAPI Backend (Port `8000`)
```bash
cd ~/Agentic-Terraform-as-a-Service
source venv/bin/activate
pkill -9 -f uvicorn 2>/dev/null || true
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Terminal 2 — Start the React Frontend (Port `8080`)
```bash
cd ~/Agentic-Terraform-as-a-Service/frontend
npm install
npm run dev
```

Click the **Web Preview** icon in the top-right corner of Google Cloud Shell → **Preview on port 8080**.

---

## Alternative Ways to Run TaaS Agent

### Option B: Built-in Google ADK Web UI
```bash
cd ~/Agentic-Terraform-as-a-Service
source venv/bin/activate
adk web --port 8080 --allow_origins "regex:https://.*\.cloudshell\.dev"
```

### Option C: Interactive Terminal CLI
```bash
cd ~/Agentic-Terraform-as-a-Service
source venv/bin/activate
python run.py
```

---

## Example Prompts to Try

- **Create a GCS Bucket**: *"Create a GCS bucket named taas-demo-raw-bkt in project solar-dialect-264808 in location asia-south2"*
- **Lookup Live Terraform Docs**: *"How do I add labels and a 30-day lifecycle rule to a GCS bucket?"*
- **Pre-Plan Code Edit**: *"Add labels env = dev and owner = data-eng to bucket.tf before planning"* (or edit directly in the **Pre-Plan Code** sidecar and click **Save to Artifacts** $\rightarrow$ **Plan**)
- **Create a BigQuery Dataset**: *"Create a BigQuery dataset named analytics_ds in project solar-dialect-264808 in location asia-south2"*
- **Create a BigQuery Table**: *"Create a BigQuery table named customer_orders in dataset analytics_ds in project solar-dialect-264808 in location asia-south2"*
- **Create a Pub/Sub Topic & Subscription**: *"Create a Pub/Sub topic named order-events-topic in solar-dialect-264808"*
- **Deactivate / Recreate**: Use the **Deactivate** and **Recreate** buttons in the **Active Resources** tab, or ask in chat: *"Delete GCS bucket taas-demo-raw-bkt in project solar-dialect-264808"*

### Inspecting or Running Terraform Manually
All generated resources live in `artifacts/gcp/` alongside `backend.tfvars`:

```bash
cd ~/Agentic-Terraform-as-a-Service/artifacts/gcp
terraform init -reconfigure -backend-config=backend.tfvars
terraform plan
```

---

## Cloud Shell Troubleshooting

### 1. `ERROR: [Errno 98] Address already in use`
If a previous `uvicorn` or `adk` process was backgrounded (e.g., via `Ctrl + Z` instead of `Ctrl + C`), kill it before restarting:
```bash
pkill -9 -f uvicorn 2>/dev/null || true
fuser -k 8000/tcp 8080/tcp 2>/dev/null || true
```
*(Always use **`Ctrl + C`** to stop running servers cleanly.)*

### 2. `501 UNIMPLEMENTED` from Vertex AI Gemini
Vertex AI Gemini models (`gemini-3.5-flash-lite` / `gemini-2.5-flash`) are served on the `global` and `us-central1` endpoints rather than regional endpoints like `asia-south2`.
- Keep `GOOGLE_CLOUD_LOCATION="global"` for Vertex AI while `TAAS_DEFAULT_REGION="asia-south2"` is used for Terraform GCP resources.
- `backend/main.py` automatically routes Vertex AI requests through `global` with fallback to `gemini-2.5-flash`.

### 3. `-bash: /usr/bin/terraform: No such file or directory`
Google Cloud Shell resets `/usr/bin/` across container restarts while preserving `$HOME`. Run `bash setup.sh` to restore the symlink from `~/.local/bin/terraform`.

---

## Safety & Governance Boundaries

- **Approved Starters Only**: All `.tf` files originate from reviewed templates in `terraform_starters/` and are rendered into `artifacts/gcp/`.
- **Single Authoritative Remote State**: All state changes are tracked in versioned Google Cloud Storage (`gs://<TAAS_STATE_BUCKET>/taas/<project_id>/gcp`).
- **AST Pre-Flight Plan Check**: Only plans modifying the expected resource address are eligible for apply; any unexpected drift or destructive change is blocked.
- **Mandatory Human Approval Gate**: Applying any plan requires explicit confirmation (`apply` / `dont apply`) verified against the plan's SHA-256 digest.
- **Non-Destructive Deactivation History**: Deactivating a resource comments out (`#`) its HCL block in `artifacts/gcp/<file>.tf` so its exact configuration can be audited or recreated with one click.

