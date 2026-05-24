import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class UpdateProjectTool(BaseZohoTool):
    """
    Tool to update details of an existing Zoho project.
    """
    async def run(self, project_id: str, name: str = None, description: str = None, start_date: str = None, end_date: str = None, status: str = None) -> dict:
        try:
            if not project_id:
                return {"success": False, "error": "project_id is required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/"
            
            # --- Robust start/end date parsing and format alignment ---
            from src.utils.date_utils import parse_date_to_zoho
            start_date = parse_date_to_zoho(start_date)
            end_date = parse_date_to_zoho(end_date)

            # Prepare update parameters (form data)
            data = {}
            if name:
                data["name"] = name
            if description is not None:
                data["description"] = description
            if start_date:
                data["start_date"] = start_date
            if end_date:
                data["end_date"] = end_date
            if status:
                data["status"] = status
                
            if not data:
                return {"success": False, "error": "No update fields provided."}
                
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=self.headers, data=data)
                if resp.status_code == 200:
                    res_data = resp.json()
                    projects = res_data.get("projects", [])
                    project = projects[0] if projects else res_data
                    logger.info(f"Successfully updated Zoho project {project_id}.")
                    return {"success": True, "project_id": project_id, "project": project}
                else:
                    logger.error(f"Failed to update Zoho project: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in UpdateProjectTool: {str(e)}")
            return {"success": False, "error": str(e)}
