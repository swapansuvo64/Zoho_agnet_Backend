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
            
            # --- Robust person_responsible assignee name resolution ---
            if person_responsible and not person_responsible.isdigit():
                try:
                    users_url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/users/"
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(users_url, headers=self.headers)
                        if resp.status_code == 200:
                            users_data = resp.json().get("users", [])
                            matched_user = None
                            # Try exact match or substring match case-insensitively
                            for u in users_data:
                                name_val = u.get("name", "").lower()
                                email_val = u.get("email", "").lower()
                                search_val = person_responsible.lower()
                                if (search_val in name_val) or (search_val in email_val) or (name_val in search_val):
                                    matched_user = u
                                    break
                            if matched_user:
                                resolved_id = matched_user.get("id") or matched_user.get("zpuid")
                                if resolved_id:
                                    logger.info(f"Resolved assignee name '{person_responsible}' to Zoho ID: {resolved_id}")
                                    person_responsible = str(resolved_id)
                except Exception as lookup_err:
                    logger.error(f"Error resolving assignee name: {str(lookup_err)}")

            # --- Robust start/end date parsing and format alignment ---
            from src.utils.date_utils import parse_date_to_zoho
            start_date = parse_date_to_zoho(start_date)
            end_date = parse_date_to_zoho(end_date)

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
                    return {"success": True, "project_id": project_id, "task": task}
                else:
                    logger.error(f"Failed to create Zoho task: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in CreateTaskTool: {str(e)}")
            return {"success": False, "error": str(e)}
