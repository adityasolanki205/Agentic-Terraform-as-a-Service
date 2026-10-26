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

### 1. Creation Workflow
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
3. Call `plan_resource` to run formatting, GCS remote backend initialization, validation, and planning.
4. Present the plan summary to the user. Do not call apply yet.
5. Prompt the user to confirm via the confirmation dropdown with choices: `apply` or `dont apply`.
6. Call `apply_resource` (gated by ADK tool confirmation). If `dont apply` is selected, cancel the operation without touching cloud resources.
7. If `apply` is selected, call `verify_resource` to verify the resource exists in Google Cloud.
8. Report the resource as READY only after verification confirms it.

### 2. Deactivation / Deletion Workflow
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

### 3. Recreation / Restoration Workflow
1. When a user asks to recreate or reactivate a previously deactivated resource, call `plan_recreate_resource`.
2. Explain that the `.tf` file was uncommented and present the creation plan.
3. Await user approval via the ADK confirmation gate.
4. Call `verify_resource` to verify the resource is once again READY in the cloud.

### 4. Listing & Auditing
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
