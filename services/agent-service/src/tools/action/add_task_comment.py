import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")


class AddTaskCommentTool(BaseZohoTool):
    """
    Tool to add a comment to a specific task in Zoho Projects.
    Calls POST /portal/{portalId}/projects/{projectId}/tasks/{taskId}/comments/
    """
    async def run(self, project_id: str, task_id: str, content: str) -> dict:
        try:
            if not project_id or not task_id or not content:
                return {"success": False, "error": "project_id, task_id, and content are all required"}

            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/comments/"

            data = {"content": content}

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=self.headers, data=data)
                if resp.status_code in (200, 201):
                    res_data = resp.json()
                    # Zoho returns: {"comments": [{...comment...}]}
                    comments = res_data.get("comments", [])
                    comment = comments[0] if comments else res_data
                    logger.info(f"Added comment to task {task_id} in project {project_id}.")
                    return {
                        "success": True,
                        "project_id": project_id,
                        "task_id": task_id,
                        "comment": comment
                    }
                else:
                    logger.error(f"Failed to add comment: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in AddTaskCommentTool: {str(e)}")
            return {"success": False, "error": str(e)}
