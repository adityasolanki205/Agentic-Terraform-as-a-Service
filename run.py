"""Interactive CLI Runner for Terraform-as-a-Service (TaaS) using Google Cloud SDK.

Runs the agent directly using standard Google Cloud Gemini SDKs (`google-genai` or `vertexai`)
without requiring `google-adk` or the `adk` CLI.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from taas_agent.tools.tools import (
    apply_resource,
    generate_resource_files,
    get_request_status,
    list_taas_resources,
    lookup_terraform_docs,
    plan_deactivate_resource,
    plan_recreate_resource,
    plan_resource,
    read_artifact_code,
    update_artifact_code,
    verify_resource,
)

SYSTEM_INSTRUCTION = """
You are the Terraform-as-a-Service (TaaS) assistant.
Help users create, manage, deactivate, and recreate approved cloud infrastructure.

Currently supported resources:
- Google Cloud BigQuery dataset ('gcp.bigquery_dataset' or 'bigquery_dataset'): dataset.tf
- Google Cloud BigQuery table ('gcp.bigquery_table' or 'bigquery_table'): table.tf
- Google Cloud Storage bucket ('gcp.storage_bucket' or 'storage_bucket'): bucket.tf
- Google Cloud Pub/Sub topic ('gcp.pubsub_topic' or 'pubsub_topic'): topic.tf
- Google Cloud Pub/Sub subscription ('gcp.pubsub_subscription' or 'pubsub_subscription'): subscription.tf

WORKFLOWS:
1. CREATE RESOURCE & PRE-PLAN CUSTOMIZATION:
   - For BigQuery datasets: collect target project ID, location, and dataset ID (resource name).
   - For BigQuery tables:
     * Collect target project ID, location, parent dataset ID, and table ID (resource name).
     * ALWAYS explicitly ask the user if they want to provide a schema for the table:
       "Would you like to provide a schema for this table? If yes, please provide it in JSON format. Otherwise, I will create the table without a schema."
     * If they do not provide a schema (or say "no", "skip", "none", "without schema"): create without schema (config={"dataset_id": dataset_id}).
     * If they provide a schema: expect it in JSON format and validate it. Pass config={"dataset_id": dataset_id, "schema": schema_json}.
   - For Storage buckets:
     * Collect target project ID, bucket name (resource name), and location.
     * Uniform bucket-level access and object versioning are enabled by default.
   - For Pub/Sub topics:
     * Collect target project ID and topic name (resource name). Location defaults to 'global'.
   - For Pub/Sub subscriptions:
     * Collect target project ID, subscription name (resource name), and parent topic name.
     * Pass parent topic in config: `config={"topic": topic_name}`. Location defaults to 'global'.
   - Call generate_resource_files.
   - CODE REVIEW & PRE-PLAN CUSTOMIZATION:
     * Display the generated Terraform code to the user in a fenced ```hcl block.
     * Inform the user: "Here is the generated Terraform code. Would you like to review, add custom configurations (e.g. tags/labels, retention, lifecycle rules), or make any changes before we run Terraform plan? You can also ask me how to configure any attribute, or say 'proceed to plan' when ready."
     * If the user asks how to configure something (e.g. "how to add tags in resource"):
       Call lookup_terraform_docs with the resource type and query.
       Explain the configuration (e.g. tags are configured using `labels = { ... }`) and present the suggested code snippet.
       Ask if they want to apply this configuration to the artifact.
     * If the user wants to make changes before plan:
       Call update_artifact_code (passing the target file and updated resource_block or code_content).
       Show the updated code to the user.
     * To inspect artifact files, call read_artifact_code.
   - When the user confirms they are ready (or says "plan", "proceed to plan", "looks good"):
     * Call plan_resource with the request_id.
   - Present the plan summary and plan SHA256 digest to the user.
   - When the user confirms apply, call apply_resource.
   - After apply, call verify_resource and report READY only when confirmed.

2. TERRAFORM DOCUMENTATION LOOKUP & CODE SUGGESTIONS:
   - When asked questions about Terraform resource attributes, syntax, or how to configure features:
     Call lookup_terraform_docs with the resource_type and query.
     Explain the setting and provide copy-pasteable HCL code suggestions.

3. DEACTIVATE / DELETE:
   - When user asks to delete a resource, call plan_deactivate_resource.
   - Explain that the specific resource block in its shared .tf file under
     artifacts/gcp has been commented out (#) to preserve configuration,
     and show the destroy plan summary.
   - When the user confirms apply, call apply_resource.
   - Call verify_resource to confirm deletion from Google Cloud.

4. RECREATE:
   - When user asks to recreate, call plan_recreate_resource.
   - Explain that the resource block in its shared .tf file under
     artifacts/gcp was uncommented and show the creation plan.
   - When the user confirms apply, call apply_resource.
   - Call verify_resource to confirm readiness.

5. LIST / STATUS:
   - Use list_taas_resources to view created resources. Only report active resources with status READY or APPLIED.
   - Do not report failed planning attempts or deleted resources as active resources.
   - Use get_request_status to check specific request progress.

Never invent shell commands or raw HCL. Always use the deterministic tools.
"""

TOOL_FUNCTIONS = {
    "generate_resource_files": generate_resource_files,
    "read_artifact_code": read_artifact_code,
    "update_artifact_code": update_artifact_code,
    "lookup_terraform_docs": lookup_terraform_docs,
    "plan_resource": plan_resource,
    "apply_resource": apply_resource,
    "plan_deactivate_resource": plan_deactivate_resource,
    "plan_recreate_resource": plan_recreate_resource,
    "verify_resource": verify_resource,
    "get_request_status": get_request_status,
    "list_taas_resources": list_taas_resources,
}

TOOL_LIST = list(TOOL_FUNCTIONS.values())



def run_with_genai_sdk():
    """Run interactive chat using the official `google-genai` SDK."""
    from google import genai
    from google.genai import types

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() in ("true", "1", "yes")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    print("\n" + "=" * 65)
    print("  Terraform-as-a-Service (TaaS) - GCP SDK Interactive Runner")
    print("=" * 65)
    print(f"  • Backend: Google GenAI SDK (Vertex AI = {use_vertex})")
    print(f"  • Project: {project or '(Default GCP credentials)'}")
    print(f"  • State Bucket: {os.getenv('TAAS_STATE_BUCKET', 'NOT SET (export TAAS_STATE_BUCKET=...)')}")
    print("=" * 65)
    print("Type your request below (or 'exit' to quit).\n")

    client = genai.Client(
        vertexai=use_vertex,
        project=project,
        location=location if use_vertex else None,
    )

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=TOOL_LIST,
        temperature=0.2,
    )

    chat = client.chats.create(model="gemini-3.5-flash-lite", config=config)

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("\nGoodbye!")
                break

            response = chat.send_message(user_input)

            # Handle function calling loop
            while response.function_calls:
                for call in response.function_calls:
                    fn_name = call.name
                    args = dict(call.args or {})
                    print(f"\n[Agent Tool Call] -> {fn_name}({args})")

                    # Human-in-the-loop approval gate for apply_resource
                    if fn_name == "apply_resource":
                        print("\n" + "!" * 60)
                        print(" [APPROVAL REQUIRED] Terraform Apply Gate")
                        print(f" Request ID  : {args.get('request_id')}")
                        print(f" Plan Digest : {args.get('plan_sha256')}")
                        print(" Confirmation Options:")
                        print("   [1] apply")
                        print("   [2] dont apply")
                        print("!" * 60)
                        choice = input(" Select decision [apply / dont apply]: ").strip().lower()
                        if choice in ("1", "apply", "y", "yes"):
                            args["confirmation"] = "apply"
                        else:
                            args["confirmation"] = "dont apply"
                        tool_result = apply_resource(**args)
                    elif fn_name in TOOL_FUNCTIONS:
                        fn = TOOL_FUNCTIONS[fn_name]
                        # Handle async functions like verify_resource
                        import inspect
                        if inspect.iscoroutinefunction(fn):
                            import asyncio
                            tool_result = asyncio.run(fn(**args))
                        else:
                            tool_result = fn(**args)
                    else:
                        tool_result = {"status": "ERROR", "message": f"Unknown tool: {fn_name}"}

                    print(f"[Tool Response]  <- Status: {tool_result.get('status', 'OK')}")

                    # Send tool result back to Gemini
                    response = chat.send_message(
                        types.Part.from_function_response(
                            name=fn_name,
                            response=tool_result,
                        )
                    )

            if response.text:
                print(f"\nAgent: {response.text}")

        except KeyboardInterrupt:
            print("\nSession ended.")
            break
        except Exception as exc:
            print(f"\n[Error] {exc}")


def run_with_vertexai_sdk():
    """Fallback runner using `google-cloud-aiplatform` (vertexai)."""
    import vertexai
    from vertexai.generative_models import GenerativeModel, Tool

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    vertexai.init(project=project, location=location)

    tools = [Tool.from_function(fn) for fn in TOOL_LIST]
    model = GenerativeModel(
        "gemini-3.5-flash-lite",
        system_instruction=SYSTEM_INSTRUCTION,
        tools=tools,
    )
    chat = model.start_chat()

    print("\n" + "=" * 65)
    print("  Terraform-as-a-Service (TaaS) - Vertex AI SDK Runner")
    print("=" * 65)
    print("Type your request below (or 'exit' to quit).\n")

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                break

            response = chat.send_message(user_input)

            while response.candidates and response.candidates[0].function_calls:
                for call in response.candidates[0].function_calls:
                    fn_name = call.name
                    args = dict(call.args)
                    print(f"\n[Agent Tool Call] -> {fn_name}({args})")

                    if fn_name == "apply_resource":
                        print("\n[APPROVAL REQUIRED] Terraform Apply Gate")
                        approval = input("Approve and execute Terraform apply? (yes/no): ").strip().lower()
                        if approval not in ("yes", "y"):
                            tool_result = {"status": "REJECTED", "message": "User declined approval."}
                        else:
                            tool_result = apply_resource(**args)
                    else:
                        fn = TOOL_FUNCTIONS.get(fn_name)
                        import inspect
                        if inspect.iscoroutinefunction(fn):
                            import asyncio
                            tool_result = asyncio.run(fn(**args))
                        else:
                            tool_result = fn(**args)

                    from vertexai.generative_models import Part
                    response = chat.send_message(
                        Part.from_function_response(
                            name=fn_name,
                            response=tool_result,
                        )
                    )

            if response.text:
                print(f"\nAgent: {response.text}")

        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"\n[Error] {exc}")


def main():
    """Detect available GCP SDK and start the agent."""
    # Check for state bucket
    if not os.getenv("TAAS_STATE_BUCKET"):
        print("[Warning] TAAS_STATE_BUCKET is not set. Remember to export TAAS_STATE_BUCKET='your-bucket'")

    try:
        import google.genai  # noqa: F401
        run_with_genai_sdk()
    except ImportError:
        try:
            import vertexai  # noqa: F401
            run_with_vertexai_sdk()
        except ImportError:
            print("\n[Error] No Google Cloud Gemini SDK found.")
            print("Please install either:")
            print("  pip install google-genai        (Recommended Google GenAI SDK)")
            print("or:")
            print("  pip install google-cloud-aiplatform (Vertex AI SDK)")
            sys.exit(1)


if __name__ == "__main__":
    main()
