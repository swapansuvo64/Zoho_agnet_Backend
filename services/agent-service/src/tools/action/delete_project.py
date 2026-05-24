import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class DeleteProjectTool(BaseZohoTool):
    """
    Tool to delete a specific project in the Zoho Projects portal.
    """
    async def run(self, project_id: str) -> dict:
        try:
            if not project_id:
                return {"success": False, "error": "project_id is required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url, headers=self.headers)
                if resp.status_code == 200:
                    logger.info(f"Successfully deleted Zoho project {project_id}.")
                    return {"success": True, "project_id": project_id, "message": f"Project {project_id} deleted successfully."}
                else:
                    logger.error(f"Failed to delete Zoho project: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in DeleteProjectTool: {str(e)}")
            return {"success": False, "error": str(e)}
