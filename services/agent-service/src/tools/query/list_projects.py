import httpx
import logging
from src.tools.base import BaseZohoTool

logger = logging.getLogger("agent-service")


def _normalize_project(p: dict) -> dict:
    """Return only the fields the agent needs — confirmed from live API."""
    return {
        "id": str(p.get("id", "")),
        "name": p.get("name", ""),
        "key": p.get("key", ""),
        "status": p.get("status", ""),
        "description": p.get("description", ""),
        "start_date": p.get("start_date", ""),
        "created_date": p.get("created_date", ""),
        "updated_date": p.get("updated_date", ""),
        "owner_name": p.get("owner_name", ""),
        "owner_id": str(p.get("owner_id", "")),
        "owner_email": p.get("owner_email", ""),
        "task_count": p.get("task_count", {}),
        "milestone_count": p.get("milestone_count", {}),
        "bug_count": p.get("bug_count", {}),
        "project_percent": p.get("project_percent", "0"),
        "billing_status": p.get("billing_status", ""),
        "currency": p.get("currency", ""),
        "role": p.get("role", ""),
        "is_public": p.get("is_public", "no"),
        "is_strict": p.get("is_strict", "no"),
        "IS_BUG_ENABLED": p.get("IS_BUG_ENABLED", False),
        "custom_status_name": p.get("custom_status_name", ""),
        "taskbug_prefix": p.get("taskbug_prefix", ""),
        "enabled_tabs": p.get("enabled_tabs", []),
    }


class ListProjectsTool(BaseZohoTool):
    """
    Tool to list all projects from the Zoho Projects portal.
    Returns a cleaned, normalized list of projects with key fields.
    """
    async def run(self) -> dict:
        try:
            portal_id = await self.get_portal_id()
            url = f"{self.base_url}/portal/{portal_id}/projects/"

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_projects = data.get("projects", [])
                    projects = [_normalize_project(p) for p in raw_projects]
                    logger.info(f"Retrieved {len(projects)} projects from Zoho.")
                    return {"success": True, "projects": projects, "count": len(projects)}
                else:
                    logger.error(f"Failed to list Zoho projects: {resp.status_code} - {resp.text}")
                    return {"success": False, "error": f"Status {resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Error in ListProjectsTool: {str(e)}")
            return {"success": False, "error": str(e)}
