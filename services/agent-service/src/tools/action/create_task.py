import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class CreateTaskTool(BaseZohoTool):
    """
    Tool to create a task in Zoho Projects under a specific project.
    """
    async def run(self, project_id: str, name: str, description: str = None, person_responsible: str = None, start_date: str = None, end_date: str = None) -> dict:
        try:
            if not project_id or not name:
                return {"success": False, "error": "Both project_id and name are required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/"
            
            # Prepare request parameters (Zoho Projects REST API accepts form data)
            data = {
                "name": name
            }
            if description:
                data["description"] = description
            if person_responsible:
                data["person_responsible"] = person_responsible
            if start_date:
                data["start_date"] = start_date
            if end_date:
                data["end_date"] = end_date
                
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=self.headers, data=data)
                if resp.status_code in (200, 201):
                    res_data = resp.json()
                    tasks = res_data.get("tasks", [])
                    task = tasks[0] if tasks else res_data
                    logger.info(f"Successfully created task '{name}' in project {project_id}.")
                    return {"success": True, "task": task}
                else:
                    logger.error(f"Failed to create Zoho task: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in CreateTaskTool: {str(e)}")
            return {"success": False, "error": str(e)}
