import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")


def _normalize_task(t: dict) -> dict:
    """
    Return only the fields the agent needs — field names confirmed from live API.
    Works for both list_tasks and get_task_details responses.
    """
    owners = t.get("details", {}).get("owners", [])
    owner_names = [o.get("name", "") for o in owners if o.get("name") != "Unassigned"]

    status = t.get("status", {})
    tasklist = t.get("tasklist", {})
    log_hours = t.get("log_hours", {})

    return {
        "id": str(t.get("id", "")),
        "id_string": t.get("id_string", ""),
        "name": t.get("name", ""),
        "key": t.get("key", ""),           # e.g. "MM1-T2"
        "description": t.get("description", ""),
        "status_name": status.get("name", ""),      # "Open" / "Closed" / "In Progress"
        "status_type": status.get("type", ""),      # "open" / "closed"
        "status_color": status.get("color_code", ""),
        "priority": t.get("priority", "None"),
        "percent_complete": t.get("percent_complete", "0"),
        "completed": t.get("completed", False),
        "start_date": t.get("start_date", ""),
        "end_date": t.get("end_date", ""),
        "duration": t.get("duration", ""),
        "duration_type": t.get("duration_type", "days"),
        "work": t.get("work", ""),              # e.g. "17:00" (hours:minutes)
        "billingtype": t.get("billingtype", "None"),
        "created_time": t.get("created_time", ""),
        "created_time_format": t.get("created_time_format", ""),
        "last_updated_time": t.get("last_updated_time", ""),
        "last_updated_time_format": t.get("last_updated_time_format", ""),
        "created_person": t.get("created_person", ""),
        "created_by_email": t.get("created_by_email", ""),
        "created_by_full_name": t.get("created_by_full_name", ""),
        "owners": owner_names,               # list of assigned person names
        "tasklist_name": tasklist.get("name", ""),
        "tasklist_id": tasklist.get("id", ""),
        "milestone_id": t.get("milestone_id", ""),
        "isparent": t.get("isparent", False),
        "subtasks": t.get("subtasks", False),
        "is_reminder_set": t.get("is_reminder_set", False),
        "is_recurrence_set": t.get("is_recurrence_set", False),
        "log_hours_billable": log_hours.get("billable_hours", "0.0"),
        "log_hours_non_billable": log_hours.get("non_billable_hours", "0.0"),
        "added_via": t.get("added_via", ""),
    }


class ListTasksTool(BaseZohoTool):
    """
    Tool to list all tasks under a specific project from Zoho Projects.
    Returns a cleaned, normalized list of tasks with key fields.
    """
    async def run(self, project_id: str) -> dict:
        try:
            if not project_id:
                return {"success": False, "error": "project_id is required"}

            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_tasks = data.get("tasks", [])
                    tasks = [_normalize_task(t) for t in raw_tasks]
                    logger.info(f"Retrieved {len(tasks)} tasks for project {project_id} from Zoho.")
                    return {"success": True, "tasks": tasks, "count": len(tasks)}
                else:
                    logger.error(f"Failed to list Zoho tasks: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in ListTasksTool: {str(e)}")
            return {"success": False, "error": str(e)}
