import httpx
import logging
from src.tools.base import BaseZohoTool
from src.tools.query.list_tasks import _normalize_task

logger = logging.getLogger("agent-service")


class GetTaskDetailsTool(BaseZohoTool):
    """
    Tool to get full details of a specific task in Zoho Projects.
    Returns a cleaned, normalized task object with all key fields.
    """
    async def run(self, project_id: str, task_id: str) -> dict:
        try:
            if not project_id or not task_id:
                return {"success": False, "error": "Both project_id and task_id are required"}

            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    tasks = data.get("tasks", [])
                    raw_task = tasks[0] if tasks else data
                    task = _normalize_task(raw_task)
                    logger.info(f"Retrieved details for task {task_id}.")
                    return {"success": True, "project_id": project_id, "task": task}
                else:
                    logger.error(f"Failed to fetch task details: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in GetTaskDetailsTool: {str(e)}")
            return {"success": False, "error": str(e)}
