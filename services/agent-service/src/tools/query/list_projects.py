import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class ListProjectsTool(BaseZohoTool):
    """
    Tool to list all projects from the Zoho Projects account.
    """
    async def run(self) -> dict:
        try:
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/"
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    projects = data.get("projects", [])
                    logger.info(f"Retrieved {len(projects)} projects from Zoho.")
                    return {"success": True, "projects": projects}
                else:
                    logger.error(f"Failed to list Zoho projects: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in ListProjectsTool: {str(e)}")
            return {"success": False, "error": str(e)}
