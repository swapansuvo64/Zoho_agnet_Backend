import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")


def _normalize_comment(raw: dict) -> dict:
    """Return a clean, slim comment object."""
    author = raw.get("added_by") or raw.get("addedby") or {}
    return {
        "id": str(raw.get("id", "")),
        "content": raw.get("content", ""),
        "author_name": author.get("name", "") if isinstance(author, dict) else str(author),
        "author_id": str(author.get("id", "")) if isinstance(author, dict) else "",
        "created_at": raw.get("time_long") or raw.get("created_time") or raw.get("time", ""),
    }


class GetTaskCommentsTool(BaseZohoTool):
    """
    Tool to fetch all comments on a specific task in Zoho Projects.
    Calls GET /portal/{portalId}/projects/{projectId}/tasks/{taskId}/comments/
    """
    async def run(self, project_id: str, task_id: str) -> dict:
        try:
            if not project_id or not task_id:
                return {"success": False, "error": "Both project_id and task_id are required"}

            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/comments/"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_comments = data.get("comments", [])
                    comments = [_normalize_comment(c) for c in raw_comments]
                    logger.info(f"Fetched {len(comments)} comment(s) for task {task_id} in project {project_id}.")
                    return {
                        "success": True,
                        "project_id": project_id,
                        "task_id": task_id,
                        "comments": comments,
                        "total": len(comments)
                    }
                else:
                    logger.error(f"Failed to fetch comments: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in GetTaskCommentsTool: {str(e)}")
            return {"success": False, "error": str(e)}
