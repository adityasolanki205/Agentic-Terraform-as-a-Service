"""ADK agent that coordinates the Terraform provisioning workflow."""

from pathlib import Path

from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import skill_toolset
from google.adk.tools.function_tool import FunctionTool

from .tools.gcp.bigquery_dataset.tools import (
    apply_bigquery_dataset,
    generate_bigquery_dataset_files,
    get_request_status,
    plan_bigquery_dataset,
    validate_bigquery_dataset_request,
    verify_bigquery_dataset,
)


provisioning_skill = load_skill_from_dir(
    Path(__file__).parent / "skills" / "terraform-provisioning"
)
provisioning_skill_tools = skill_toolset.SkillToolset(
    skills=[provisioning_skill]
)

# ADK pauses for an explicit user confirmation before invoking this tool.
apply_tool = FunctionTool(
    apply_bigquery_dataset,
    require_confirmation=True,
)

root_agent = Agent(
    name="TaaSAgent",
    model="gemini-3.5-flash-lite",
    description=(
        "Creates approved Google Cloud resources with reviewable Terraform "
        "artifacts and an explicit plan approval step."
    ),
    instruction="""
You are the Terraform-as-a-Service assistant. Follow the
terraform-provisioning skill for every infrastructure request.

Currently, the only supported resource is a Google Cloud BigQuery dataset.
Collect the project ID, dataset ID, and location explicitly from the user.
Ask for missing values; never infer them from previous messages or the active
gcloud configuration.

Use the validation tool before generating files. After generation, use the
Terraform plan tool and show the plan summary before applying anything.
The apply tool has an ADK confirmation gate. Do not call it until you have
presented the plan and the user has clearly asked to proceed. Use the same
request ID and plan digest returned by the plan tool.

After apply succeeds, use the verification tool. Say the resource is ready only
if verification reports READY. Otherwise report the current status accurately.

Never write or modify Terraform code yourself. Never ask a tool to execute a
user-provided shell command. Do not create extra resources, change IAM, create
the state bucket, or push artifacts to GitHub.
""",
    tools=[
        provisioning_skill_tools,
        validate_bigquery_dataset_request,
        generate_bigquery_dataset_files,
        plan_bigquery_dataset,
        apply_tool,
        verify_bigquery_dataset,
        get_request_status,
    ],
)
