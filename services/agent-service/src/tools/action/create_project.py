import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class CreateProjectTool(BaseZohoTool):
    """
    Tool to create a new project in the Zoho Projects portal.
    """
    async def run(self, name: str, description: str = None, start_date: str = None, end_date: str = None) -> dict:
        try:
            if not name:
                return {"success": False, "error": "Project name is required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/"
            
            # --- Robust start/end date parsing and format alignment ---
            from src.utils.date_utils import parse_date_to_zoho
            start_date = parse_date_to_zoho(start_date)
            end_date = parse_date_to_zoho(end_date)

            # Prepare request parameters (form data)
            data = {
                "name": name
            }
            if description:
                data["description"] = description
            if start_date:
                data["start_date"] = start_date
            if end_date:
                data["end_date"] = end_date
                
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=self.headers, data=data)
                if resp.status_code in (200, 201):
                    res_data = resp.json()
                    projects = res_data.get("projects", [])
                    project = projects[0] if projects else res_data
                    logger.info(f"Successfully created Zoho project '{name}'.")
                    return {"success": True, "project": project}
                else:
                    logger.error(f"Failed to create Zoho project: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in CreateProjectTool: {str(e)}")
            return {"success": False, "error": str(e)}
