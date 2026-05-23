import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")

class UpdateTaskTool(BaseZohoTool):
    """
    Tool to update details of an existing Zoho Projects task.
    """
    async def run(self, project_id: str, task_id: str, name: str = None, description: str = None, person_responsible: str = None, start_date: str = None, end_date: str = None, status: str = None) -> dict:
        try:
            if not project_id or not task_id:
                return {"success": False, "error": "Both project_id and task_id are required"}
                
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/"
            
            # Prepare update parameters (form parameters)
            data = {}
            if name:
                data["name"] = name
            if description:
                data["description"] = description
            if person_responsible:
                data["person_responsible"] = person_responsible
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
                    tasks = res_data.get("tasks", [])
                    task = tasks[0] if tasks else res_data
                    logger.info(f"Successfully updated task {task_id} in project {project_id}.")
                    return {"success": True, "task": task}
                else:
                    logger.error(f"Failed to update Zoho task: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in UpdateTaskTool: {str(e)}")
            return {"success": False, "error": str(e)}
