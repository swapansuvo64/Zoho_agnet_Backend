import httpx
import logging
from src.tools.base import BaseZohoTool
from src.tools.query.list_tasks import _normalize_task

logger = logging.getLogger("agent-service")

class GetTaskUtilisationTool(BaseZohoTool):
    """
    Tool to get task timesheet utilization/logs from Zoho Projects.
    """
    async def run(self, project_id: str, task_id: str = None) -> dict:
        try:
            if not project_id:
                return {"success": False, "error": "project_id is required"}
                
            portal_id = await self.get_portal_id()
            
            async with httpx.AsyncClient() as client:
                # If task_id is None, null, or "all", fetch all tasks in the project
                if not task_id or str(task_id).lower() == "all":
                    url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/"
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_tasks = data.get("tasks", [])
                        utilisation_list = []
                        for t in raw_tasks:
                            norm_task = _normalize_task(t)
                            utilisation_list.append({
                                "task_id": norm_task.get("id"),
                                "name": norm_task.get("name"),
                                "percent_complete": norm_task.get("percent_complete"),
                                "planned_work": norm_task.get("work"),
                                "duration": norm_task.get("duration"),
                                "duration_type": norm_task.get("duration_type"),
                                "billable_hours": norm_task.get("log_hours_billable"),
                                "non_billable_hours": norm_task.get("log_hours_non_billable"),
                                "status": norm_task.get("status_name")
                            })
                        logger.info(f"Retrieved utilisation for {len(utilisation_list)} tasks in project {project_id}.")
                        return {"success": True, "project_id": project_id, "utilisation": utilisation_list, "is_all_tasks": True}
                    else:
                        logger.error(f"Failed to fetch task list for utilisation: {resp.status_code} - {resp.text}")
                        return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
                else:
                    # Specific task_id requested. Fetch specific task details to avoid 403 on timesheet logs API.
                    url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/"
                    resp = await client.get(url, headers=self.headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        tasks = data.get("tasks", [])
                        raw_task = tasks[0] if tasks else data
                        norm_task = _normalize_task(raw_task)
                        
                        utilisation_summary = {
                            "task_id": norm_task.get("id"),
                            "name": norm_task.get("name"),
                            "percent_complete": norm_task.get("percent_complete"),
                            "planned_work": norm_task.get("work"),
                            "duration": norm_task.get("duration"),
                            "duration_type": norm_task.get("duration_type"),
                            "billable_hours": norm_task.get("log_hours_billable"),
                            "non_billable_hours": norm_task.get("log_hours_non_billable"),
                            "status": norm_task.get("status_name")
                        }
                        logger.info(f"Retrieved utilisation for specific task {task_id}.")
                        return {"success": True, "project_id": project_id, "utilisation": [utilisation_summary], "is_all_tasks": False}
                    else:
                        logger.error(f"Failed to fetch task details for utilisation: {resp.status_code} - {resp.text}")
                        return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
                        
        except Exception as e:
            logger.error(f"Error in GetTaskUtilisationTool: {str(e)}")
            return {"success": False, "error": str(e)}

