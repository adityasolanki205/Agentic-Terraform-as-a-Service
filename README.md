# Agentic Terraform as a Service (TaaS)

A multi-cloud, declarative Terraform-as-a-Service platform using Gemini ADK and approved Terraform starters.
Currently supports Google Cloud BigQuery datasets and BigQuery tables with generic tools ready to expand to more GCP and AWS data engineering resources.

## How it works

1. **Create Resource**: The ADK agent collects the target project ID, location, parent dataset ID (for tables), resource name, and asks for an optional JSON schema.
2. **Artifact Generation**: Generic tools manage infrastructure within a single dedicated folder: `artifacts/gcp/`. It maintains a single `main.tf`, `variables.tf`, `dataset.tf` (where all datasets are maintained), and `table.tf` (where all tables are maintained).
3. **Plan & Pre-flight Inspection**: Terraform initializes the existing versioned GCS remote backend (`taas/<project_id>/gcp`) and runs `terraform plan`. The AST plan validator verifies that *only* the requested resource creation is planned (other resources in the shared file show as `no-op`).
4. **Approval Gate**: The agent shows the plan summary. Applying requires explicit user approval via ADK's confirmation prompt (`apply` / `dont apply`).
5. **Apply & Remote State**: Terraform applies the plan, creating the cloud resource and updating the authoritative remote state in GCS (`gs://<bucket>/taas/<project_id>/gcp`).
6. **Cloud Verification**: An asynchronous verification tool queries the Google Cloud API to confirm the resource and schema are ready.
7. **Deactivate / Delete**: When a user asks to delete a resource, the tool comments out only that specific resource block (`#`) in `dataset.tf` or `table.tf` and plans a destroy. Applying it removes the resource from Google Cloud and updates the GCS state, while preserving the commented code in `dataset.tf` / `table.tf` for full auditability and easy recreation.
8. **Recreate**: When asked to recreate, the tool simply uncomments that resource block in `dataset.tf` or `table.tf` and runs a creation plan and apply.

## Project layout

```text
taas_agent/
  agent.py                             # ADK Agent (gemini-3.5-flash-lite, approval gates)
  skills/terraform-provisioning/SKILL.md # Provisioning & deactivation guidance
  tools/
    tools.py                           # Generic lifecycle tools (generate, plan, apply, deactivate, recreate, verify)
terraform_starters/                    # Approved Terraform templates (source of truth)
  common/
    main.tf                            # GCS backend & Google provider starter
    variables.tf                       # Shared variables starter
  gcp/
    bigquery_dataset/
      dataset.tf                       # Dataset resource starter template
    bigquery_table/
      table.tf                         # Table resource starter template
    storage_bucket/
      bucket.tf                        # GCS bucket starter template
    pubsub_topic/
      topic.tf                         # Pub/Sub topic starter template
    pubsub_subscription/
      subscription.tf                  # Pub/Sub subscription starter template
artifacts/                             # Created strictly at RUNTIME from starters
  gcp/                                 # Single runtime folder for all GCP resources
    main.tf                            # Copied at runtime from common/main.tf
    variables.tf                       # Copied at runtime from common/variables.tf
    dataset.tf                         # All BigQuery datasets (commented when deleted)
    table.tf                           # All BigQuery tables (commented when deleted)
    bucket.tf                          # All GCS buckets (commented when deleted)
    topic.tf                           # All Pub/Sub topics (commented when deleted)
    subscription.tf                    # All Pub/Sub subscriptions (commented when deleted)
    backend.tfvars                     # GCS state config
    terraform.tfvars                   # Runtime project & location vars
.taas/requests/                        # Local request records, metadata, and saved plans
```

## Quick Start (One-Click Setup)

Run the automated setup script in Google Cloud Shell to install Terraform v1.9.8, setup the virtual environment, install dependencies, and configure environment variables:

```bash
bash setup.sh
```

## Manual Setup in Google Cloud Shell

1. Open the project folder and activate your Python environment:

   ```bash
   cd ~/Agentic-Terraform-as-a-Service
   source venv/bin/activate
   ```

2. Check Terraform is available (Terraform v1.5+ is required; v1.9.8 recommended). In Google Cloud Shell, Terraform is installed persistently to `~/.local/bin/terraform` so it survives container restarts:

   ```bash
   terraform version
   ```

   If missing or broken after a container reset, install it persistently:

   ```bash
   mkdir -p ~/.local/bin && curl -sLo ~/.local/bin/terraform.zip https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip && unzip -qo ~/.local/bin/terraform.zip -d ~/.local/bin/ && rm ~/.local/bin/terraform.zip && chmod +x ~/.local/bin/terraform && sudo ln -sf ~/.local/bin/terraform /usr/bin/terraform && hash -r
   ```

3. Install the Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure Gemini through Vertex AI (using Cloud Shell default credentials):

   ```bash
   export GOOGLE_GENAI_USE_VERTEXAI=TRUE
   export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
   export GOOGLE_CLOUD_LOCATION="global"
   ```

5. Set the name of your existing, versioned Terraform state GCS bucket:

   ```bash
   export TAAS_STATE_BUCKET="YOUR_EXISTING_STATE_BUCKET"
   ```

6. Start the agent:

   **Option A: Google ADK Web UI (Recommended for Cloud Shell)**
   
   Start the server on port **8080** with Cloud Shell regex CORS authorization:
   ```bash
   adk web --port 8080 --allow_origins "regex:https://.*\.cloudshell\.dev"
   ```
   Then click **Web Preview** (top-right button in Cloud Shell) -> **Preview on port 8080**.

   **Option B: Interactive Terminal CLI**
   
   ```bash
   python run.py
   ```

7. Ask to create, delete, or recreate resources!
   - To create a dataset: *"Create a BigQuery dataset named tform in project solar-dialect-264808 in location asia-south2"*
   - To create a table: *"Create a BigQuery table named customer_orders in dataset tform in project solar-dialect-264808 in location asia-south2"*
   - To delete a table: *"Delete BigQuery table customer_orders in dataset tform in project solar-dialect-264808"*
   - To recreate a table: *"Recreate BigQuery table customer_orders in dataset tform in project solar-dialect-264808"*
   - To list: *"List all created resources"*

### Inspecting or Running Terraform Manually

All resources live in `artifacts/gcp/` alongside `backend.tfvars`:

```bash
cd artifacts/gcp
terraform init -reconfigure -backend-config=backend.tfvars
terraform plan
```

## Cloud Shell Troubleshooting

### 1. `[Errno 98] Address already in use`
A previous `adk web` or server process is still bound to port 8080 or 8000. Kill it using:
```bash
fuser -k 8000/tcp 8080/tcp 2>/dev/null || kill -9 $(lsof -t -i:8080) 2>/dev/null || pkill -f "adk"
```

### 2. `-bash: /usr/bin/terraform: No such file or directory`
Google Cloud Shell wipes ephemeral container paths like `/usr/bin/` upon restart, but preserves your `$HOME` (`~`) volume. Run `bash setup.sh` to restore persistent symlinks instantly.

### 3. `ValueError: No API key was provided`
Google Cloud GenAI requires Vertex AI routing when running without a direct API key. Ensure `GOOGLE_GENAI_USE_VERTEXAI=TRUE` is set:
```bash
export GOOGLE_GENAI_USE_VERTEXAI="TRUE"
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
```
*(Note: `taas_agent` also auto-detects and sets this from `.env` on import).*

Use the web interface for the POC. The future EnterpriseGPT integration is out
of scope for this phase.

## Safety boundaries

- Supported resources: Google Cloud BigQuery datasets (`gcp.bigquery_dataset`) and BigQuery tables (`gcp.bigquery_table`).
- The agent asks for all required values rather than inferring a project,
  dataset ID, table ID, or location.
- Terraform runs as fixed argument lists; the model cannot provide shell
  commands or raw Terraform source.
- Only a plan that modifies the expected resource address (`google_bigquery_dataset.requested` or `google_bigquery_table.requested`) is eligible for apply. Any unexpected additional, update, or delete action is strictly blocked.
- Apply uses the verified SHA-256 plan hash and requires explicit user confirmation (`apply` / `dont apply`).
- No cloud resources are created until a user approves the apply tool call.
- Request metadata and plan files are local to the development environment.
  The Terraform state itself is remote in versioned GCS.
- Notifications in this POC are replies in the ADK chat.

## Current scope

Phase 1 is Google Cloud only (BigQuery datasets and tables). EnterpriseGPT
integration, additional Google Cloud resources, and AWS are planned for later phases.
