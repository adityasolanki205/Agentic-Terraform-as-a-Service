"""Parameterized BigQuery tools for Agentic DataOps (ServiceNow Incident Analytics).

Ported directly from Agentic_DataOps with strict anti-SQL-injection parameterization
via BigQuery QueryJobConfig.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

OPEN_STATUSES = ["New", "In Progress", "On Hold"]


def _get_bq_config() -> tuple[str, str, str]:
    project_id = (
        os.getenv("BQ_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("PROJECT_ID")
        or "solar-dialect-264808"
    )
    dataset_id = os.getenv("BQ_DATASET_ID", "servicenow_itsm")
    table_id = os.getenv("BQ_TABLE_ID", "incidents")
    return project_id, dataset_id, table_id


def _build_date_filter(
    date_column: str,
    time_scope: str,
    month: int | None = None,
    year: int | None = None,
) -> tuple[list[str], list]:
    """Build parameterized UTC timestamp bounds for opened_date or closed_date."""
    scope = (time_scope or "ALL").upper().strip()
    if scope not in {"MONTH", "ALL"}:
        raise ValueError("time_scope must be 'MONTH' or 'ALL'.")

    conditions: list[str] = []
    parameters: list = []

    if scope == "MONTH":
        if month is None or year is None:
            raise ValueError("For MONTH scope, both month and year are required.")
        month = int(month)
        year = int(year)
        if month < 1 or month > 12:
            raise ValueError("month must be between 1 and 12.")
        if year < 2000 or year > 2100:
            raise ValueError("year must be a valid four-digit year.")

        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        conditions.append(f"{date_column} >= @start_date")
        conditions.append(f"{date_column} < @end_date")
        parameters.extend(
            [
                bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", start_date),
                bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", end_date),
            ]
        )

    return conditions, parameters


# ==============================================================================
# 1. Incident Summary Specialist Tools
# ==============================================================================


def count_all_incidents() -> dict:
    """Return the total number of incidents in the ServiceNow table."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"
        query = f"SELECT COUNT(*) AS total_incidents FROM {table_name}"
        result = client.query(query).result()
        row = list(result)[0]
        return {
            "status": "SUCCESS",
            "total_incidents": int(row["total_incidents"]),
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def count_open_incidents_by_group() -> dict:
    """Return the count of currently open incidents ('New', 'In Progress', 'On Hold') by assignment group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        query = f"""
            SELECT
                assignment_group,
                COUNT(*) AS open_incident_count
            FROM {table_name}
            WHERE status IN UNNEST(@open_statuses)
            GROUP BY assignment_group
            ORDER BY open_incident_count DESC
        """
        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("open_statuses", "STRING", OPEN_STATUSES)
            ]
        )
        result = client.query(query, job_config=config).result()
        groups = [
            {
                "assignment_group": row["assignment_group"],
                "open_incident_count": int(row["open_incident_count"]),
            }
            for row in result
        ]
        return {
            "status": "SUCCESS",
            "period": "ALL AVAILABLE DATA",
            "open_incidents_by_assignment_group": groups,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


# ==============================================================================
# 2. Opened Incidents Specialist Tools
# ==============================================================================


def count_opened_incidents(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
) -> dict:
    """Count incidents opened in a given time_scope ('MONTH' or 'ALL') and optional assignment_group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("opened_date", time_scope, month, year)
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT COUNT(*) AS total_opened_incidents FROM {table_name} {where_clause}"

        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()
        row = list(result)[0]
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "assignment_group": assignment_group or "ALL GROUPS",
            "total_opened_incidents": int(row["total_opened_incidents"]),
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_opened_incident_details(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
    limit: int = 50,
) -> dict:
    """Retrieve row-level incident details filtered by opened_date."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        limit = max(1, min(int(limit), 200))
        conditions, parameters = _build_date_filter("opened_date", time_scope, month, year)
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                incident_id,
                opened_date,
                closed_date,
                status,
                assignment_group,
                assignee,
                category,
                priority,
                short_description
            FROM {table_name}
            {where_clause}
            ORDER BY opened_date DESC
            LIMIT @limit
        """
        parameters.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()

        incidents = []
        for row in result:
            incidents.append(
                {
                    "incident_id": row["incident_id"],
                    "opened_date": row["opened_date"].isoformat() if row["opened_date"] else None,
                    "closed_date": row["closed_date"].isoformat() if row["closed_date"] else None,
                    "status": row["status"],
                    "assignment_group": row["assignment_group"],
                    "assignee": row["assignee"],
                    "category": row["category"],
                    "priority": row["priority"],
                    "short_description": row["short_description"],
                }
            )
        return {
            "status": "SUCCESS",
            "count": len(incidents),
            "incidents": incidents,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


# ==============================================================================
# 3. Closed Incidents Specialist Tools
# ==============================================================================


def count_closed_incidents(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
) -> dict:
    """Count closed incidents filtered by closed_date and optional assignment_group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("closed_date", time_scope, month, year)
        conditions.append("status = 'Closed'")
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"SELECT COUNT(*) AS total_closed_incidents FROM {table_name} {where_clause}"

        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()
        row = list(result)[0]
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "assignment_group": assignment_group or "ALL GROUPS",
            "total_closed_incidents": int(row["total_closed_incidents"]),
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def count_closed_incidents_by_group(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
) -> dict:
    """Return closed incident counts grouped by assignment_group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("closed_date", time_scope, month, year)
        conditions.append("status = 'Closed'")
        where_clause = f"WHERE {' AND '.join(conditions)}"

        query = f"""
            SELECT
                assignment_group,
                COUNT(*) AS closed_incident_count
            FROM {table_name}
            {where_clause}
            GROUP BY assignment_group
            ORDER BY closed_incident_count DESC
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()
        groups = [
            {
                "assignment_group": row["assignment_group"],
                "closed_incident_count": int(row["closed_incident_count"]),
            }
            for row in result
        ]
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "closed_incidents_by_assignment_group": groups,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_closed_incident_details(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
    limit: int = 50,
) -> dict:
    """Retrieve row-level closed incident records sorted by closed_date DESC."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        limit = max(1, min(int(limit), 200))
        conditions, parameters = _build_date_filter("closed_date", time_scope, month, year)
        conditions.append("status = 'Closed'")
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
            SELECT
                incident_id,
                opened_date,
                closed_date,
                status,
                assignment_group,
                assignee,
                category,
                priority,
                short_description
            FROM {table_name}
            {where_clause}
            ORDER BY closed_date DESC
            LIMIT @limit
        """
        parameters.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()

        incidents = []
        for row in result:
            incidents.append(
                {
                    "incident_id": row["incident_id"],
                    "opened_date": row["opened_date"].isoformat() if row["opened_date"] else None,
                    "closed_date": row["closed_date"].isoformat() if row["closed_date"] else None,
                    "status": row["status"],
                    "assignment_group": row["assignment_group"],
                    "assignee": row["assignee"],
                    "category": row["category"],
                    "priority": row["priority"],
                    "short_description": row["short_description"],
                }
            )
        return {
            "status": "SUCCESS",
            "count": len(incidents),
            "incidents": incidents,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


# ==============================================================================
# 4. MTTR (Mean Time To Resolve) Specialist Tools
# ==============================================================================


def calculate_mttr(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
) -> dict:
    """Compute Mean Time To Resolve (MTTR) in hours and days for closed incidents."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("closed_date", time_scope, month, year)
        conditions.extend(
            [
                "status = 'Closed'",
                "opened_date IS NOT NULL",
                "closed_date IS NOT NULL",
            ]
        )
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
            SELECT
                COUNT(*) AS incident_count,
                AVG(TIMESTAMP_DIFF(closed_date, opened_date, SECOND)) AS avg_mttr_seconds
            FROM {table_name}
            {where_clause}
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()
        row = list(result)[0]

        incident_count = int(row["incident_count"] or 0)
        avg_seconds = float(row["avg_mttr_seconds"] or 0.0)
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "assignment_group": assignment_group or "ALL GROUPS",
            "closed_incidents_used": incident_count,
            "mttr_hours": round(avg_seconds / 3600, 2),
            "mttr_days": round(avg_seconds / 86400, 2),
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def calculate_mttr_by_group(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
) -> dict:
    """Compute Mean Time To Resolve (MTTR) broken down by assignment group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("closed_date", time_scope, month, year)
        conditions.extend(
            [
                "status = 'Closed'",
                "opened_date IS NOT NULL",
                "closed_date IS NOT NULL",
            ]
        )
        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
            SELECT
                assignment_group,
                COUNT(*) AS closed_incident_count,
                AVG(TIMESTAMP_DIFF(closed_date, opened_date, SECOND)) AS avg_mttr_seconds
            FROM {table_name}
            {where_clause}
            GROUP BY assignment_group
            ORDER BY avg_mttr_seconds DESC
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()

        groups = []
        for row in result:
            sec = float(row["avg_mttr_seconds"] or 0.0)
            groups.append(
                {
                    "assignment_group": row["assignment_group"],
                    "closed_incident_count": int(row["closed_incident_count"]),
                    "mttr_hours": round(sec / 3600, 2),
                    "mttr_days": round(sec / 86400, 2),
                }
            )
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "mttr_by_assignment_group": groups,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


# ==============================================================================
# 5. Open Ticket Aging Specialist Tools
# ==============================================================================


def calculate_open_incident_aging(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
    assignment_group: str | None = None,
) -> dict:
    """Calculate average backlog age in days for currently open incidents."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("opened_date", time_scope, month, year)
        conditions.extend(
            [
                "status IN UNNEST(@open_statuses)",
                "opened_date IS NOT NULL",
            ]
        )
        parameters.append(
            bigquery.ArrayQueryParameter("open_statuses", "STRING", OPEN_STATUSES)
        )
        if assignment_group:
            conditions.append("LOWER(assignment_group) = LOWER(@assignment_group)")
            parameters.append(
                bigquery.ScalarQueryParameter("assignment_group", "STRING", assignment_group)
            )

        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
            SELECT
                COUNT(*) AS open_incident_count,
                AVG(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), opened_date, SECOND)) AS avg_age_seconds
            FROM {table_name}
            {where_clause}
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()
        row = list(result)[0]

        incident_count = int(row["open_incident_count"] or 0)
        avg_seconds = float(row["avg_age_seconds"] or 0.0)
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "assignment_group": assignment_group or "ALL GROUPS",
            "open_incident_count": incident_count,
            "average_aging_days": round(avg_seconds / 86400, 2),
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def calculate_open_incident_aging_by_group(
    time_scope: str = "ALL",
    month: int | None = None,
    year: int | None = None,
) -> dict:
    """Calculate open incident backlog aging in days grouped by assignment group."""
    try:
        project_id, dataset_id, table_id = _get_bq_config()
        client = bigquery.Client(project=project_id)
        table_name = f"`{project_id}.{dataset_id}.{table_id}`"

        conditions, parameters = _build_date_filter("opened_date", time_scope, month, year)
        conditions.extend(
            [
                "status IN UNNEST(@open_statuses)",
                "opened_date IS NOT NULL",
            ]
        )
        parameters.append(
            bigquery.ArrayQueryParameter("open_statuses", "STRING", OPEN_STATUSES)
        )
        where_clause = f"WHERE {' AND '.join(conditions)}"
        query = f"""
            SELECT
                assignment_group,
                COUNT(*) AS open_incident_count,
                AVG(TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), opened_date, SECOND)) AS avg_age_seconds
            FROM {table_name}
            {where_clause}
            GROUP BY assignment_group
            ORDER BY avg_age_seconds DESC
        """
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        result = client.query(query, job_config=config).result()

        groups = []
        for row in result:
            sec = float(row["avg_age_seconds"] or 0.0)
            groups.append(
                {
                    "assignment_group": row["assignment_group"],
                    "open_incident_count": int(row["open_incident_count"]),
                    "average_aging_days": round(sec / 86400, 2),
                }
            )
        return {
            "status": "SUCCESS",
            "period": f"{int(year)}-{int(month):02d}" if time_scope.upper() == "MONTH" and year and month else "ALL AVAILABLE DATA",
            "open_aging_by_assignment_group": groups,
        }
    except Exception as exc:
        return {"status": "ERROR", "message": str(exc)}


def get_dataops_dashboard_kpis() -> dict:
    """Aggregate high-level ServiceNow KPIs for the Agentic DataOps UI header cards."""
    project_id, dataset_id, table_id = _get_bq_config()
    total_res = count_all_incidents()
    open_groups_res = count_open_incidents_by_group()
    mttr_res = calculate_mttr("ALL")
    aging_res = calculate_open_incident_aging("ALL")

    open_groups = open_groups_res.get("open_incidents_by_assignment_group", [])
    total_open = sum(g.get("open_incident_count", 0) for g in open_groups)
    total_incidents = total_res.get("total_incidents", 0)

    return {
        "status": "SUCCESS" if total_res.get("status") == "SUCCESS" else "WARN",
        "table": f"{project_id}.{dataset_id}.{table_id}",
        "total_incidents": total_incidents,
        "total_open_incidents": total_open,
        "total_closed_incidents": max(0, total_incidents - total_open),
        "mttr_hours": mttr_res.get("mttr_hours", 0.0),
        "mttr_days": mttr_res.get("mttr_days", 0.0),
        "average_aging_days": aging_res.get("average_aging_days", 0.0),
        "open_by_group": open_groups,
        "error": total_res.get("message") if total_res.get("status") == "ERROR" else None,
    }

