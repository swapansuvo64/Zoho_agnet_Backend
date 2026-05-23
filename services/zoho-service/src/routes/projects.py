"""
Projects router — provides popup-ready detail for any project by ID.

Endpoints:
  GET /zoho/projects                        → list all projects (summary cards)
  GET /zoho/projects/{project_id}           → full project detail popup
  GET /zoho/projects/{project_id}/members   → project members list
"""
import logging
from fastapi import APIRouter, Depends

from src.routes.dependencies import get_zoho_token
from src.controllers.zoho_client import (
    fetch_projects,
    fetch_project_detail,
    fetch_project_members,
)

logger = logging.getLogger("zoho-service")
router = APIRouter(prefix="/zoho/projects", tags=["Projects"])


@router.get("", summary="List all Zoho projects")
async def list_projects(zoho_token: str = Depends(get_zoho_token)):
    """
    Returns a normalized list of all projects in the Zoho portal.
    The agent embeds project IDs in its summaries; the frontend calls this
    to populate the projects sidebar / overview cards.
    """
    projects = await fetch_projects(zoho_token)
    return {"success": True, "count": len(projects), "projects": projects}


@router.get("/{project_id}", summary="Get full project detail")
async def get_project(project_id: str, zoho_token: str = Depends(get_zoho_token)):
    """
    Returns full normalized detail for a single project.
    Called when the user clicks on a project name/link in the chat popup.
    """
    project = await fetch_project_detail(project_id, zoho_token)
    return {"success": True, "project": project}


@router.get("/{project_id}/members", summary="List project members")
async def list_members(project_id: str, zoho_token: str = Depends(get_zoho_token)):
    """
    Returns all users assigned to a project.
    Called when the user clicks 'View Members' in the chat popup.
    """
    members = await fetch_project_members(project_id, zoho_token)
    return {"success": True, "count": len(members), "members": members}


@router.get("/{project_id}/members/{member_id}", summary="Get specific member detail")
async def get_member(
    project_id: str,
    member_id: str,
    zoho_token: str = Depends(get_zoho_token),
):
    """
    Returns full normalized detail for a single member inside a project.
    Called when the user clicks on a member's name/link in the chat popup.
    """
    from fastapi import HTTPException
    members = await fetch_project_members(project_id, zoho_token)
    for m in members:
        if m.get("id") == member_id or m.get("zpuid") == member_id:
            return {"success": True, "member": m}
    raise HTTPException(
        status_code=404,
        detail=f"Member {member_id} not found in project {project_id}.",
    )

