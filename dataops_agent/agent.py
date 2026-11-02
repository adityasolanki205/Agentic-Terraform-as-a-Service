"""ADK Multi-Agent Supervisor and Gemini Runner for Agentic DataOps (ServiceNow ITSM Analytics)."""

import os
from .tools import (
    calculate_mttr,
    calculate_mttr_by_group,
    calculate_open_incident_aging,
    calculate_open_incident_aging_by_group,
    count_all_incidents,
    count_closed_incidents,
    count_closed_incidents_by_group,
    count_open_incidents_by_group,
    count_opened_incidents,
    get_closed_incident_details,
    get_opened_incident_details,
)

if not os.getenv("GEMINI_API_KEY"):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

DATAOPS_SYSTEM_INSTRUCTION = """
You are the ServiceNow Incident Analytics Master Agent (Agentic DataOps).
You help developers and operations teams analyze ServiceNow ITSM incident data stored in Google BigQuery (`servicenow_itsm.incidents`).

VALID ASSIGNMENT GROUPS:
- Database Admin
- Network Support
- Service Desk
- Cloud Infrastructure
- Cyber Security
- Application Dev

KEY RULES & DISAMBIGUATION:
1. Never invent or execute raw SQL strings directly; always use the deterministic BigQuery tools.
2. Strictly distinguish between:
   - **Opened Incidents** (incidents created in a date range -> use `count_opened_incidents` or `get_opened_incident_details`).
   - **Currently Open Incidents** (active backlog with status 'New', 'In Progress', or 'On Hold' -> use `count_open_incidents_by_group` or `calculate_open_incident_aging`).
   - **Closed Incidents** (status = 'Closed' -> use `count_closed_incidents`, `count_closed_incidents_by_group`, or `get_closed_incident_details`).
   - **MTTR (Mean Time To Resolve)** (resolution time for closed tickets -> use `calculate_mttr` or `calculate_mttr_by_group`).
   - **Aging** (elapsed backlog age for open tickets -> use `calculate_open_incident_aging` or `calculate_open_incident_aging_by_group`).
3. TIME SCOPE RULES:
   - If the user asks about a specific month (e.g. "August 2026"), pass `time_scope="MONTH"`, `month=8`, `year=2026`.
   - If the user mentions a month WITHOUT a year (e.g. "in August"), politely ask which year they want before running a monthly query.
   - If the user does not specify a date range or says "all" / "overall" / "everything", pass `time_scope="ALL"`.
4. COUNT BY DEFAULT, DETAILS ON DEMAND:
   - Return summary counts or metrics by default.
   - Only call `get_opened_incident_details` or `get_closed_incident_details` when the user explicitly asks to list tickets, IDs, or ticket details.
   - Format tables and metrics cleanly using Markdown.
"""

DATAOPS_TOOLS = [
    count_all_incidents,
    count_open_incidents_by_group,
    count_opened_incidents,
    get_opened_incident_details,
    count_closed_incidents,
    count_closed_incidents_by_group,
    get_closed_incident_details,
    calculate_mttr,
    calculate_mttr_by_group,
    calculate_open_incident_aging,
    calculate_open_incident_aging_by_group,
]

try:
    from google.adk import Agent

    incident_summary_agent = Agent(
        name="IncidentSummaryAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Specialist for overall incident counts and open backlog breakdown by assignment group.",
        instruction="Use count_all_incidents and count_open_incidents_by_group to report high-level incident counts.",
        tools=[count_all_incidents, count_open_incidents_by_group],
    )

    opened_incidents_agent = Agent(
        name="OpenedIncidentAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Specialist for tickets opened in a specific period or across all data.",
        instruction="Use count_opened_incidents by default and get_opened_incident_details only when ticket rows are requested.",
        tools=[count_opened_incidents, get_opened_incident_details],
    )

    closed_incidents_agent = Agent(
        name="ClosedIncidentAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Specialist for closed ticket counts, group breakdowns, and closed ticket details.",
        instruction="Use count_closed_incidents, count_closed_incidents_by_group, and get_closed_incident_details.",
        tools=[
            count_closed_incidents,
            count_closed_incidents_by_group,
            get_closed_incident_details,
        ],
    )

    mttr_agent = Agent(
        name="MTTRAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Specialist for calculating Mean Time to Resolve (MTTR) on closed incidents.",
        instruction="Use calculate_mttr and calculate_mttr_by_group to report MTTR in hours and days.",
        tools=[calculate_mttr, calculate_mttr_by_group],
    )

    aging_agent = Agent(
        name="AgingAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Specialist for calculating active backlog aging on currently open incidents.",
        instruction="Use calculate_open_incident_aging and calculate_open_incident_aging_by_group to report aging in days.",
        tools=[calculate_open_incident_aging, calculate_open_incident_aging_by_group],
    )

    dataops_root_agent = Agent(
        name="ServiceNowMasterAgent",
        model=os.getenv("DATAOPS_MODEL", "gemini-3.5-flash-lite"),
        description="Lead ServiceNow incident analytics supervisor agent.",
        instruction=DATAOPS_SYSTEM_INSTRUCTION,
        sub_agents=[
            incident_summary_agent,
            opened_incidents_agent,
            closed_incidents_agent,
            mttr_agent,
            aging_agent,
        ],
    )
except ImportError:
    dataops_root_agent = None


_DATAOPS_SESSIONS: dict[str, object] = {}


def chat_with_dataops_agent(message: str, session_id: str = "default") -> dict:
    """Execute a conversational turn with the Agentic DataOps assistant."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    project = (
        os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("PROJECT_ID")
        or os.getenv("BQ_PROJECT_ID")
        or "solar-dialect-264808"
    )
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    model_name = os.getenv("DATAOPS_MODEL", "gemini-2.5-flash")

    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        client = genai.Client(vertexai=True, project=project, location=location)

    if session_id not in _DATAOPS_SESSIONS:
        _DATAOPS_SESSIONS[session_id] = client.chats.create(
            model=model_name,
            config=types.GenerateContentConfig(
                system_instruction=DATAOPS_SYSTEM_INSTRUCTION,
                tools=DATAOPS_TOOLS,
                temperature=0.1,
            ),
        )

    chat = _DATAOPS_SESSIONS[session_id]
    response = chat.send_message(message)
    return {
        "status": "SUCCESS",
        "response": response.text or "Query completed.",
    }

