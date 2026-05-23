import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class ListProjectMembersTool(BaseZohoTool):
    """
    Tool to list all users/members associated with a specific project in Zoho Projects.
    """
    async def run(self, project_id: str) -> dict:
        try:
            if not project_id:
                return {"success": False, "error": "project_id is required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/users/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    users = data.get("users", [])
                    logger.info(f"Retrieved {len(users)} users for project {project_id}.")
                    return {"success": True, "members": users}
                else:
                    logger.error(f"Failed to list project users: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in ListProjectMembersTool: {str(e)}")
            return {"success": False, "error": str(e)}
