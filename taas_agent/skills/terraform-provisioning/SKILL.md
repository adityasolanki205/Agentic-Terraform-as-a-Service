---
name: terraform-provisioning
description: Guide users through creating, managing, deactivating, and recreating approved cloud resources with Terraform.
---

# Terraform Provisioning Skill

## Purpose

Help the user manage cloud infrastructure through a deterministic, approval-based Terraform-as-a-Service workflow.
Python tools perform all operations against approved starters. Do not write raw Terraform code yourself or claim an operation succeeded unless a tool confirms it.

## Supported Resources

- **Google Cloud BigQuery Dataset** (`gcp.bigquery_dataset`):
  Collect: Google Cloud project ID, dataset ID (resource name), and location (e.g. `US`, `us-central1`).

## Resource Rules

- Create or delete only what the user explicitly requested.
- Do not invent Terraform code, shell commands, resource types, or input parameters.
- Ask for any missing parameters; never infer or guess them.
- If a value is invalid or unclear, ask the user to clarify.

## Workflows

### 1. Creation Workflow
1. Confirm the resource type and required values with the user.
2. Call `generate_resource_files` to generate reviewable Terraform artifacts from the approved starter.
3. Call `plan_resource` to run formatting, GCS remote backend initialization, validation, and planning.
4. Present the plan summary to the user. Do not call apply yet.
5. Apply only after the user approves the exact plan via the ADK confirmation gate.
6. Call `verify_resource` to verify the resource exists in Google Cloud.
7. Report the resource as READY only after verification confirms it.

### 2. Deactivation / Deletion Workflow
1. When a user asks to delete a resource, call `plan_deactivate_resource`.
2. Explain to the user that the Terraform `.tf` file has been commented out (`#`) to preserve the configuration for future recreation, and that applying the plan will destroy the cloud resource and update the GCS state file.
3. Present the destruction plan summary to the user.
4. Wait for the user to approve via the ADK confirmation gate.
5. Call `verify_resource` to confirm that the resource is removed from Google Cloud.
6. Report the resource as DELETED while informing the user that the code remains saved for recreation.

### 3. Recreation / Restoration Workflow
1. When a user asks to recreate or reactivate a previously deactivated resource, call `plan_recreate_resource`.
2. Explain that the `.tf` file was uncommented and present the creation plan.
3. Await user approval via the ADK confirmation gate.
4. Call `verify_resource` to verify the resource is once again READY in the cloud.

### 4. Listing & Auditing
1. Use `list_taas_resources` when the user asks what resources exist or have been created.
2. Use `get_request_status` to inspect a specific request's progress.

## Artifact and State Handling

- Generated Terraform artifacts reside under `artifacts/` for manual git commits and review.
- The authoritative Terraform state is stored remotely in an existing, versioned GCS bucket under `taas/<project_id>/<resource_type>/<resource_name>`.
- Deletions and creations update this state file automatically.
