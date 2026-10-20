---
name: terraform-provisioning
description: Guide users through creating approved cloud resources with Terraform.
---

# Terraform Provisioning Skill

## Purpose

Help the user request a cloud resource through a clear, approval-based workflow.
Python tools perform the operations. Do not write Terraform code yourself or
claim an operation succeeded unless a tool confirms it.

## Supported resources

For this first POC, the only supported resource is a Google Cloud BigQuery
dataset. If the user asks for anything else, explain it is not supported yet.

## Information to collect

For a BigQuery dataset, collect:

- Google Cloud project ID
- Dataset ID
- Dataset location

Ask for any missing values. Do not guess them from conversation context or the
active `gcloud` configuration.

## Resource rules

- Create only the BigQuery dataset the user requested.
- Do not add tables, buckets, service accounts, IAM changes, networks, or other
  resources unless the user explicitly requests them and the platform supports
  them.
- Use only the approved BigQuery dataset Terraform starter.
- Do not invent Terraform code, shell commands, resource types, or input values.
- If a value is invalid or unclear, ask the user to correct or clarify it.

## Provisioning workflow

1. Confirm the resource type and required values with the user.
2. Use the tool to validate the request and create reviewable Terraform artifact
   files from the approved starter.
3. Use the tool to run Terraform formatting, initialization, validation, and
   planning.
4. Show the plan summary to the user. Do not apply it yet.
5. Apply only after the user clearly approves that exact plan using the ADK
   confirmation prompt.
6. If the plan changes, show the new plan and ask for approval again.
7. After apply, report that the request is still being checked.
8. Report the resource as ready only after the verification tool confirms it
   exists in the requested project and location.
9. If any step fails, explain which step failed. Do not say the resource is
   ready.

## Artifact handling

Give the user the generated Terraform files so they can review and commit them
to GitHub themselves. Do not push to GitHub or claim that files have been
committed.

## State handling

Use the configured shared Terraform state for the project when it is available.
Do not create a state bucket, change IAM, or choose a new backend automatically.
If the backend is not configured, stop before Terraform initialization and ask
the user to complete the approved setup step.

## Current implementation status

The tools validate requests, generate Terraform artifacts, run formatting and
validation, create a plan, gate apply on ADK confirmation, and verify the
BigQuery dataset after apply. Verification retries asynchronously during the
tool call. The tool reports the request as still verifying if it cannot confirm
the dataset within its retry window.

The application does not create a GCS bucket or change IAM. Email notifications
and an independent background worker are not included; successful verification
is reported to the user in the ADK chat.
