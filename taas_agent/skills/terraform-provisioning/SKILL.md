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
  Collect: Google Cloud project ID, dataset ID (resource name), and location (e.g. `US`, `asia-south2`).
  Managed in `artifacts/gcp/dataset.tf`.
- **Google Cloud BigQuery Table** (`gcp.bigquery_table`):
  Collect: Google Cloud project ID, location, parent dataset ID, and table ID (resource name).
  Managed in `artifacts/gcp/table.tf`.
  Schema handling:
  - ALWAYS ask the user if they want to provide a schema.
  - If they do NOT provide a schema (or say "no", "skip", "none", "without schema"): create the table without a schema (`config={"dataset_id": dataset_id}`).
  - If they DO provide a schema: expect it in JSON format (e.g. `[{"name": "id", "type": "STRING", "mode": "REQUIRED"}]`). Pass `config={"dataset_id": dataset_id, "schema": schema_json}`.
- **Google Cloud Storage Bucket** (`gcp.storage_bucket`):
  Collect: Google Cloud project ID, bucket name (resource name), and location (e.g. `asia-south2`, `US`).
  Managed in `artifacts/gcp/bucket.tf`.
  Defaults: uniform bucket-level access = true, object versioning = true.
- **Google Cloud Pub/Sub Topic** (`gcp.pubsub_topic`):
  Collect: Google Cloud project ID, topic name (resource name). Location can default to `global`.
  Managed in `artifacts/gcp/topic.tf`.
- **Google Cloud Pub/Sub Subscription** (`gcp.pubsub_subscription`):
  Collect: Google Cloud project ID, subscription name (resource name), and parent topic name.
  Pass parent topic in config: `config={"topic": topic_name}`. Location can default to `global`.
  Managed in `artifacts/gcp/subscription.tf`.

## Resource Rules

- Create or delete only what the user explicitly requested.
- Do not invent Terraform code, shell commands, resource types, or input parameters.
- Ask for any missing parameters; never infer or guess them.
- If a value is invalid or unclear, ask the user to clarify.

## Workflows

### 1. Creation & Pre-Plan Customization Workflow
1. Confirm the resource type and required values with the user:
   - For BigQuery datasets: collect `project_id`, `location`, and `dataset_id`.
   - For BigQuery tables: collect `project_id`, `location`, parent `dataset_id`, and `table_id` (resource name).
     * Ask: *"Would you like to provide a schema for this table? If yes, please provide it in JSON format. Otherwise, I will create the table without a schema."*
   - For Storage buckets: collect `project_id`, `bucket_name` (resource name), and `location`.
   - For Pub/Sub topics: collect `project_id` and `topic_name` (resource name).
   - For Pub/Sub subscriptions: collect `project_id`, `subscription_name` (resource name), and parent `topic_name`.
2. Call `generate_resource_files` to generate reviewable Terraform artifacts from the approved starter.
   - For tables, pass `config={"dataset_id": dataset_id}` (and include `"schema": schema` if provided).
   - For subscriptions, pass `config={"topic": topic_name}`.
3. **Pre-Plan Code Review & Customization**:
   - Present the generated Terraform HCL code to the user.
   - Ask the user if they would like to review, add custom configurations (e.g. tags/labels, retention policies, lifecycle rules), or make changes before running `terraform plan`.
   - If the user asks how to configure any attribute (e.g. *"how to add tags in resource"*), call `lookup_terraform_docs(resource_type, query)`:
     * Explain the Terraform attribute syntax (e.g. GCP uses `labels = { ... }` for metadata tags).
     * Provide the suggested copy-pasteable HCL snippet.
     * Offer to add the configuration to the artifact file.
   - If the user wants to add or modify configurations in the code, call `update_artifact_code`:
     * Pass the target file name (e.g. `bucket.tf`, `table.tf`, `dataset.tf`, `topic.tf`, `subscription.tf`) and the updated `resource_block` or `code_content`.
     * `update_artifact_code` automatically formats the file using `terraform fmt`.
     * Display the updated code to the user.
   - If the user asks to inspect current artifact files, call `read_artifact_code`.
4. When the user confirms they are ready (e.g. *"proceed to plan"*, *"run plan"*, *"looks good"*), call `plan_resource` to run formatting, GCS remote backend initialization, validation, and planning.
5. Present the plan summary and SHA256 digest to the user. Do not call apply yet.
6. Prompt the user to confirm via the confirmation dropdown with choices: `apply` or `dont apply`.
7. Call `apply_resource` (gated by ADK tool confirmation). If `dont apply` is selected, cancel the operation without touching cloud resources.
8. If `apply` is selected, call `verify_resource` to verify the resource exists in Google Cloud.
9. Report the resource as READY only after verification confirms it.

### 2. Terraform Documentation Lookup & Suggestion Workflow
1. At any time, if the user asks how to configure a Terraform resource, what options/arguments are available, or asks for code examples (e.g., *"how do I set lifecycle rules in GCS bucket?"*, *"how to add tags to pubsub topic"*):
   - Call `lookup_terraform_docs(resource_type, query)`.
   - The tool queries the official Google provider documentation live in real-time, checks attribute definitions, and synthesizes accurate, copy-pasteable HCL snippets.
   - Explain the concept to the user in chat and present the suggested HCL code block.


### 3. Deactivation / Deletion Workflow
1. When a user asks to delete a resource, call `plan_deactivate_resource`.
   - For tables, provide `project_id`, `resource_name=table_id`, `resource_type="gcp.bigquery_table"`, and `dataset_id`.
   - For buckets, provide `project_id`, `resource_name=bucket_name`, and `resource_type="gcp.storage_bucket"`.
   - For topics, provide `project_id`, `resource_name=topic_name`, and `resource_type="gcp.pubsub_topic"`.
   - For subscriptions, provide `project_id`, `resource_name=sub_name`, and `resource_type="gcp.pubsub_subscription"`.
2. Explain to the user that the Terraform `.tf` file has been commented out (`#`) to preserve the configuration for future recreation, and that applying the plan will destroy the cloud resource and update the GCS state file.
3. Present the destruction plan summary to the user.
4. Wait for the user to approve via the ADK confirmation gate (`apply` / `dont apply`).
5. Call `verify_resource` to confirm that the resource is removed from Google Cloud.
6. Report the resource as DELETED while informing the user that the code remains saved for recreation.

### 4. Recreation / Restoration Workflow
1. When a user asks to recreate or reactivate a previously deactivated resource, call `plan_recreate_resource`.
2. Explain that the `.tf` file was uncommented and present the creation plan.
3. Await user approval via the ADK confirmation gate.
4. Call `verify_resource` to verify the resource is once again READY in the cloud.

### 5. Listing & Auditing
1. Use `list_taas_resources` when the user asks what resources exist or have been created. Only report active resources returned with status `READY` or `APPLIED`.
2. Do not report failed planning attempts (`PLAN_FAILED`), failed applies, unapplied drafts, or deleted resources as active resources.
3. Use `get_request_status` to inspect a specific request's progress or troubleshoot a failed request.

## Artifact and State Handling

- The `artifacts/` folder is **created on runtime only** when `generate_resource_files` is executed. It is not pre-populated in Git.
- All configuration is sourced directly from approved starters in `terraform_starters/`:
  - `main.tf`: Copied at runtime from `terraform_starters/common/main.tf`.
  - `variables.tf`: Copied at runtime from `terraform_starters/common/variables.tf`.
  - `dataset.tf`: Single file for all BigQuery datasets, rendered from `terraform_starters/gcp/bigquery_dataset/`.
  - `table.tf`: Single file for all BigQuery tables, rendered from `terraform_starters/gcp/bigquery_table/`.
  - `bucket.tf`: Single file for all GCS buckets, rendered from `terraform_starters/gcp/storage_bucket/`.
  - `topic.tf`: Single file for all Pub/Sub topics, rendered from `terraform_starters/gcp/pubsub_topic/`.
  - `subscription.tf`: Single file for all Pub/Sub subscriptions, rendered from `terraform_starters/gcp/pubsub_subscription/`.
  - Active resources are appended as resource blocks.
  - Deleted resources have their block commented out with `#`.
  - Recreated resources have their block uncommented.
  - `terraform.tfvars`: Project and location variables rendered at runtime.
  - `backend.tfvars`: Backend bucket and project-scoped state prefix (`taas/<project_id>/gcp`) rendered at runtime.
- The authoritative Terraform state is stored remotely in an existing, versioned GCS bucket under `taas/<project_id>/gcp`.
- Every creation, deactivation, and recreation updates this shared state file automatically.
