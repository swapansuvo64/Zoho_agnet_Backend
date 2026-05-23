import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class DeleteTaskTool(BaseZohoTool):
    """
    Tool to delete a specific task in Zoho Projects.
    """
    async def run(self, project_id: str, task_id: str) -> dict:
        try:
            if not project_id or not task_id:
                return {"success": False, "error": "Both project_id and task_id are required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, headers=self.headers)
                if resp.status_code == 200:
                    logger.info(f"Successfully deleted task {task_id} under project {project_id}.")
                    return {"success": True, "message": f"Task {task_id} deleted successfully."}
                else:
                    logger.error(f"Failed to delete Zoho task: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in DeleteTaskTool: {str(e)}")
            return {"success": False, "error": str(e)}
