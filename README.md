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
  main.tf
  variables.tf
artifacts/                 # Generated Terraform files
.taas/requests/             # Local request records and saved plans
```

Each future resource gets its own Python tool folder and its own Terraform
starter folder. The agent instructions and skill explain the workflow; Python
tools enforce the supported operations.

## Local setup

Use a fresh Python environment in Google Cloud Shell. Activate the environment,
then install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

Configure ADK to use Vertex AI with your selected project and model location:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT="YOUR_PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="global"
```

The project ID requested in chat is still collected explicitly; the environment
variable above is for Gemini model access.

## GCS Terraform state

Before planning, set `TAAS_STATE_BUCKET` to the name of an existing GCS bucket
that is approved for Terraform state:

```bash
export TAAS_STATE_BUCKET="YOUR_EXISTING_STATE_BUCKET"
```

The bucket must have object versioning enabled. The GCS backend uses a single
default Terraform state at the prefix `taas/<project-id>` and provides state
locking. The application does not create the bucket or modify its IAM settings.

## Run the ADK web interface

From the project root, with the environment activated and configuration set:

```bash
adk web
```

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
