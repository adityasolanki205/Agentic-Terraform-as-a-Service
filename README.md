# Agentic Terraform as a Service (TaaS)

A beginner-friendly Google Cloud proof of concept using Gemini ADK and approved
Terraform starters. The first supported resource is a BigQuery dataset.

## How it works

1. The ADK agent collects the project ID, dataset ID, and location from the user.
2. Python tools validate the values and copy the approved Terraform starter into
   a request-specific artifact folder.
3. The Terraform plan tool initializes the existing GCS backend, validates the
   files, and creates a plan. The tool rejects any plan that contains a change
   other than creating the requested dataset.
4. The agent presents the plan. The apply tool has an ADK confirmation gate and
   applies the saved plan only after the user confirms the tool call.
5. An asynchronous verification tool checks that the dataset exists in the
   requested project and location. The agent reports ready only after the check
   succeeds.

The app does not create a state bucket, change IAM, or push files to GitHub.
Generated Terraform artifacts are written under `artifacts/` for review and
manual commit. Request records and saved plan files are written under `.taas/`.

## Project layout

```text
taas_agent/
  agent.py
  skills/terraform-provisioning/SKILL.md
  tools/gcp/bigquery_dataset/tools.py
terraform_starters/gcp/bigquery_dataset/
  bigquery_dataset.tf
terraform_starters/common/
  main.tf
  variables.tf
artifacts/                 # Generated Terraform files
.taas/requests/             # Local request records and saved plans
```

`terraform_starters/common/main.tf` and `variables.tf` hold configuration
shared by all resources. Each resource folder contains only that resource's
Terraform block. The generator copies the common files and the selected
resource file together into one generated Terraform root folder, because
Terraform reads `.tf` files from the same directory.

Each future resource gets its own Python tool folder and its own Terraform
starter folder. The agent instructions and skill explain the workflow; Python
tools enforce the supported operations.

## Run it in Google Cloud Shell

These steps install the Python packages and start the ADK web interface. They
do not create a cloud resource.

1. Open the project folder and activate your Python environment:

   ```bash
   cd ~/Agentic-Terraform-as-a-Service
   source taas-env/bin/activate
   ```

   If your environment has a different name, replace `taas-env` with its name.

2. Check Terraform is available. This project was written for Terraform 1.5 or
   newer. If the command is missing, install Terraform using the
   [official HashiCorp instructions](https://developer.hashicorp.com/terraform/install).

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

6. Start the chat interface from the project root:

   ```bash
   adk web
   ```

7. Ask for a BigQuery dataset. Provide the target project ID, dataset ID, and
   location when asked. Review the generated files and plan. Apply happens only
   after you approve the plan in the ADK interface.

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
