import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class ListTasksTool(BaseZohoTool):
    """
    Tool to list all tasks under a specific project from Zoho Projects.
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
                    tasks = data.get("tasks", [])
                    logger.info(f"Retrieved {len(tasks)} tasks for project {project_id} from Zoho.")
                    return {"success": True, "tasks": tasks}
                else:
                    logger.error(f"Failed to list Zoho tasks: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in ListTasksTool: {str(e)}")
            return {"success": False, "error": str(e)}
