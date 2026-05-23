import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class GetTaskUtilisationTool(BaseZohoTool):
    """
    Tool to get task timesheet utilization/logs from Zoho Projects.
    """
    async def run(self, project_id: str, task_id: str) -> dict:
        try:
            if not project_id or not task_id:
                return {"success": False, "error": "Both project_id and task_id are required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/logs/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # Try to fetch standard timelogs structure
                    timelogs = data.get("timelogs", {}) or {}
                    logs = timelogs.get("tasklogs", []) if isinstance(timelogs, dict) else []
                    logger.info(f"Retrieved {len(logs)} logs for task {task_id}.")
                    return {"success": True, "utilisation": logs}
                else:
                    logger.error(f"Failed to fetch task utilization logs: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in GetTaskUtilisationTool: {str(e)}")
            return {"success": False, "error": str(e)}
