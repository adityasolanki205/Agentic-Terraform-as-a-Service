# Agentic Terraform as a Service (TaaS)

A multi-cloud, declarative Terraform-as-a-Service platform using Gemini ADK and approved Terraform starters.
Currently supports Google Cloud BigQuery datasets with generic tools ready to expand to more GCP and AWS data engineering resources.

## How it works

1. **Create Resource**: The ADK agent collects the target project ID, location, and resource name.
2. **Artifact Generation**: Generic tools copy the approved Terraform starter and common configuration into a dedicated artifact directory under `artifacts/`.
3. **Plan & Pre-flight Inspection**: Terraform initializes the existing versioned GCS remote backend and runs `terraform plan`. The AST plan validator verifies that *only* the requested resource creation is planned.
4. **Approval Gate**: The agent shows the plan summary. Applying requires explicit user approval via ADK's confirmation prompt.
5. **Apply & Remote State**: Terraform applies the plan, creating the cloud resource and updating the authoritative remote state in GCS (`gs://<bucket>/taas/<project_id>/<resource_type>/<resource_name>`).
6. **Cloud Verification**: An asynchronous verification tool queries the Google Cloud API to confirm the resource is ready.
7. **Deactivate / Delete**: When a user asks to delete a resource, the tool comments out the resource block (`#`) in the `.tf` file and plans a destroy. Applying it removes the resource from Google Cloud and updates the GCS state, while preserving the commented code in `artifacts/` for full auditability and easy recreation.
8. **Recreate**: When asked to recreate, the tool simply uncomments the `.tf` file and runs a creation plan and apply.

## Project layout

```text
taas_agent/
  agent.py                             # ADK Agent (gemini-3.5-flash-lite, approval gates)
  skills/terraform-provisioning/SKILL.md # Provisioning & deactivation guidance
  tools/
    __init__.py
    tools.py                           # Generic lifecycle tools (generate, plan, apply, deactivate, recreate, verify)
terraform_starters/
  common/
    main.tf                            # GCS backend & Google provider
    variables.tf                       # Shared variables
  gcp/
    bigquery_dataset/
      bigquery_dataset.tf              # Resource starter
artifacts/                             # Generated Terraform files (commented upon deactivation)
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

2. Check Terraform is available. (Terraform v1.5+ is required; v1.9.8 recommended):

   ```bash
   terraform version
   ```

3. Install the Python dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure Gemini through Vertex AI. The active `gcloud` project here is for
   Gemini access only; the agent will still ask the user to provide the target
   resource project ID in chat.

   ```bash
   export GOOGLE_GENAI_USE_VERTEXAI=TRUE
   export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
   export GOOGLE_CLOUD_LOCATION="global"
   ```

5. Set the name of the already-created, approved Terraform state bucket:

   ```bash
   export TAAS_STATE_BUCKET="YOUR_EXISTING_STATE_BUCKET"
   ```

   The bucket must have object versioning enabled. The tool will stop before
   Terraform initialization if the bucket is missing or not versioned. It does
   not create the bucket or change its permissions.

6. Start the interactive chat interface using the Google Cloud SDK:

   ```bash
   python run.py
   ```

   *(Note: For the Google ADK Web UI in Cloud Shell, run: `adk web --allow_origins "regex:https://.*\.cloudshell\.dev"`)*

7. Ask to create, delete, or recreate resources!
   - To create: *"Create a BigQuery dataset named sales_data in project my-project in location US"*
   - To delete: *"Delete BigQuery dataset sales_data in project my-project"*
   - To recreate: *"Recreate BigQuery dataset sales_data in project my-project"*
   - To list: *"List all created resources"*

### Inspecting or Running Terraform Manually in Artifact Folders

Each artifact directory under `artifacts/` contains the generated `.tf` files and a `backend.tfvars` file:

```bash
cd artifacts/<artifact_folder>
terraform init -reconfigure -backend-config=backend.tfvars
terraform plan
```

The Google Cloud SDKs use the credentials available in Cloud Shell. The account
needs permission to create the requested BigQuery dataset and access the
approved state bucket. No separate application authentication setup is included
in this POC.

Use the web interface for the POC. The future EnterpriseGPT integration is out
of scope for this phase.

## Safety boundaries

- Only BigQuery dataset creation is supported.
- The agent asks for all required values rather than inferring a project,
  dataset ID, or location.
- Terraform runs as fixed argument lists; the model cannot provide shell
  commands or Terraform source.
- Only a plan that creates `google_bigquery_dataset.requested` is eligible for
  apply. Any additional, update, or delete action is blocked.
- Apply uses the saved plan and requires ADK tool confirmation.
- No cloud resources are created until a user runs the agent and confirms the
  apply tool call.
- Request metadata and plan files are local to the development environment.
  The Terraform state itself is remote in GCS.
- Notifications in this POC are replies in the ADK chat. Email integration is
  not included.

## Current scope

Phase 1 is Google Cloud only, beginning with a BigQuery dataset. EnterpriseGPT
integration, additional Google Cloud resources, and AWS are later phases.
