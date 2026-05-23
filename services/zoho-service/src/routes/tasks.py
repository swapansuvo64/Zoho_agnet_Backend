"""
Tasks router — provides popup-ready task detail for any task by ID.

Endpoints:
  GET /zoho/projects/{project_id}/tasks                       → list all tasks in a project
  GET /zoho/projects/{project_id}/tasks/{task_id}             → full task detail popup
"""
import logging
from fastapi import APIRouter, Depends

from src.routes.dependencies import get_zoho_token
from src.controllers.zoho_client import fetch_tasks, fetch_task_detail

logger = logging.getLogger("zoho-service")
router = APIRouter(prefix="/zoho/projects", tags=["Tasks"])


@router.get("/{project_id}/tasks", summary="List all tasks in a project")
async def list_tasks(project_id: str, zoho_token: str = Depends(get_zoho_token)):
    """
    Returns a normalized list of all tasks in a project.
    The agent embeds project_id + task IDs in its summaries; the frontend
    calls this to show the task list panel popup.
    """
    tasks = await fetch_tasks(project_id, zoho_token)
    return {"success": True, "count": len(tasks), "tasks": tasks}


@router.get("/{project_id}/tasks/{task_id}", summary="Get full task detail")
async def get_task(
    project_id: str,
    task_id: str,
    zoho_token: str = Depends(get_zoho_token),
):
    """
    Returns full normalized detail for a single task.
    Called when the user clicks on a task name/link in the chat bubble popup.

    Key fields returned (confirmed from live API):
      - id, name, key, description
      - status_name, status_type, status_color
      - priority, percent_complete, completed
      - start_date, end_date, duration, duration_type
      - created_person, created_by_email, assigned_to[]
      - tasklist_name, tasklist_id
      - log_hours_billable, log_hours_non_billable
      - link_web  (direct Zoho UI URL for the task)
    """
    task = await fetch_task_detail(project_id, task_id, zoho_token)
    return {"success": True, "task": task}
