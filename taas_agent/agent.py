"""ADK agent that coordinates the generic Terraform-as-a-Service provisioning workflow."""

from pathlib import Path

try:
    from google.adk import Agent
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools import skill_toolset
    from google.adk.tools.function_tool import FunctionTool
    _HAS_ADK = True
except ImportError:
    Agent = None
    _HAS_ADK = False

from .tools import (
    apply_resource,
    generate_resource_files,
    get_request_status,
    list_taas_resources,
    plan_deactivate_resource,
    plan_recreate_resource,
    plan_resource,
    verify_resource,
)

if _HAS_ADK:
    provisioning_skill = load_skill_from_dir(
        Path(__file__).parent / "skills" / "terraform-provisioning"
    )
    provisioning_skill_tools = skill_toolset.SkillToolset(
        skills=[provisioning_skill]
    )

    # ADK pauses for explicit user confirmation before applying any Terraform plan
    apply_tool = FunctionTool(
        apply_resource,
        require_confirmation=True,
    )

    root_agent = Agent(
        name="TaaSAgent",
        model="gemini-3.5-flash-lite",
        description=(
            "Manages approved cloud resources through a declarative Terraform-as-a-Service "
            "workflow with reviewable artifacts, approval gates, deactivation, and verification."
        ),
        instruction="""
        You are the Terraform-as-a-Service (TaaS) assistant. Follow the
        terraform-provisioning skill for every infrastructure request.

        Currently supported resources:
        - Google Cloud BigQuery dataset ('gcp.bigquery_dataset' or 'bigquery_dataset')

        WORKFLOWS:

        1. CREATE RESOURCE:
           - Collect target project ID, location, and resource name (e.g. dataset ID) from the user.
           - Ask for any missing values; never guess or infer project IDs or names.
           - Call generate_resource_files with the validated inputs.
           - Call plan_resource using the returned request_id.
           - Present the plan summary to the user. Do NOT apply immediately.
           - The apply_resource tool has an ADK confirmation gate. Only call it when the user
             explicitly approves the presented plan.
           - After apply succeeds, call verify_resource to verify the resource in the cloud.
           - Report ready ONLY when verify_resource returns READY.

        2. DELETE / DEACTIVATE RESOURCE:
           - When a user asks to delete a resource, call plan_deactivate_resource.
           - Explain to the user that the Terraform code has been commented out (#) in the
             artifacts folder so it can be restored anytime, and that applying will destroy
             the resource in Google Cloud and update the state in GCS.
           - Present the destruction plan summary.
           - Await user approval via the apply confirmation gate.
           - After apply succeeds, call verify_resource to confirm the resource is gone.

        3. RECREATE / RESTORE RESOURCE:
           - When a user asks to restore or recreate a previously deactivated resource,
             call plan_recreate_resource.
           - Explain that the code was uncommented and present the creation plan.
           - Await user approval via the apply confirmation gate.
           - Apply and verify.

        4. LIST / STATUS:
           - Use list_taas_resources to view managed resources.
           - Use get_request_status to check specific request progress.

        SAFETY RULES:
        - Never write or invent raw Terraform code yourself.
        - Never execute shell commands or ask tools to execute shell scripts.
        - Remote state in GCS is strictly version-controlled and updated through Terraform.
        """,
        tools=[
            provisioning_skill_tools,
            generate_resource_files,
            plan_resource,
            apply_tool,
            plan_deactivate_resource,
            plan_recreate_resource,
            verify_resource,
            get_request_status,
            list_taas_resources,
        ],
    )
else:
    root_agent = None
