"""
Zoho Projects API client — all raw HTTP calls live here.
Normalizers return clean, frontend-friendly dicts using confirmed field names.
"""
import httpx
import logging
from fastapi import HTTPException, status

from src.config.settings import settings

logger = logging.getLogger("zoho-service")

BASE = settings.ZOHO_BASE_URL


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _get(url: str, token: str) -> dict:
    """Generic async GET with error handling."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=_headers(token))
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Zoho token expired or invalid.")
        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail=f"Zoho permission denied: {resp.text}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Resource not found in Zoho.")
        raise HTTPException(status_code=502, detail=f"Zoho API error {resp.status_code}: {resp.text}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HTTP error calling Zoho: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Zoho API unreachable: {str(e)}")


_PORTAL_ID_CACHE = None


async def _get_portal_id(token: str) -> str:
    global _PORTAL_ID_CACHE
    if _PORTAL_ID_CACHE is not None:
        return _PORTAL_ID_CACHE
    data = await _get(f"{BASE}/portals/", token)
    portals = data.get("portals", [])
    if not portals:
        raise HTTPException(status_code=502, detail="No Zoho portals found for this account.")
    _PORTAL_ID_CACHE = str(portals[0]["id"])
    return _PORTAL_ID_CACHE


# ─────────────────────────────────────────────────────────────
# Normalizers  (confirmed field names from live API 2026-05-23)
# ─────────────────────────────────────────────────────────────

def _norm_project(p: dict) -> dict:
    # Safely convert project_percent to int
    pct = p.get("project_percent", "0")
    try:
        percent_complete = int(pct) if pct else 0
    except (ValueError, TypeError):
        percent_complete = 0

    return {
        "id": str(p.get("id", "")),
        "name": p.get("name", "").strip(),
        "key": p.get("key", ""),
        "status": p.get("status", ""),
        "custom_status_name": p.get("custom_status_name", ""),
        "custom_status_color": p.get("custom_status_color", ""),
        "description": p.get("description", ""),
        "start_date": p.get("start_date", ""),
        "end_date": p.get("end_date", ""),
        "created_date": p.get("created_date", ""),
        "updated_date": p.get("updated_date", ""),
        "created_person": p.get("created_by", ""),
        "owner_name": p.get("owner_name", ""),
        "owner_email": p.get("owner_email", ""),
        "owner_id": str(p.get("owner_id", "")),
        "task_count": p.get("task_count", {}),
        "milestone_count": p.get("milestone_count", {}),
        "bug_count": p.get("bug_count", {}),
        "project_percent": pct,
        "percent_complete": percent_complete,
        "billing_status": p.get("billing_status", ""),
        "currency": p.get("currency", ""),
        "currency_symbol": p.get("currency_symbol", ""),
        "role": p.get("role", ""),
        "is_public": p.get("is_public", "no"),
        "IS_BUG_ENABLED": p.get("IS_BUG_ENABLED", False),
        "taskbug_prefix": p.get("taskbug_prefix", ""),
        "enabled_tabs": p.get("enabled_tabs", []),
        "business_hours": p.get("business_hours", {}),
        "cascade_setting": p.get("cascade_setting", {}),
        "layout_details": p.get("layout_details", {}),
        "link_web": p.get("link", {}).get("web", {}).get("url", ""),
    }



def _norm_task(t: dict) -> dict:
    owners = t.get("details", {}).get("owners", [])
    assigned = [
        {
            "name": o.get("full_name") or o.get("name", ""),
            "zpuid": str(o.get("zpuid", "")),
            "email": o.get("email", ""),
            "id": str(o.get("id", "")),
            "work": str(o.get("work", ""))
        }
        for o in owners
        if (o.get("full_name") or o.get("name")) not in ("Unassigned", "", None)
    ]
    status = t.get("status", {})
    tasklist = t.get("tasklist", {})
    log_hours = t.get("log_hours", {})
    followers = t.get("task_followers", {}).get("FOLLOWERS", [])

    pct = t.get("percent_complete", "0")
    try:
        percent_complete = int(pct) if pct else 0
    except (ValueError, TypeError):
        percent_complete = 0

    return {
        "id": str(t.get("id", "")),
        "name": t.get("name", ""),
        "key": t.get("key", ""),
        "description": t.get("description", ""),
        "status_name": status.get("name", ""),
        "status_type": status.get("type", ""),
        "status_color": status.get("color_code", ""),
        "priority": t.get("priority", "None"),
        "percent_complete": percent_complete,
        "completed": t.get("completed", False),
        "start_date": t.get("start_date", ""),
        "end_date": t.get("end_date", ""),
        "created_time": t.get("created_time", ""),
        "created_time_format": t.get("created_time_format", ""),
        "last_updated_time": t.get("last_updated_time", ""),
        "last_updated_time_format": t.get("last_updated_time_format", ""),
        "created_person": t.get("created_person", ""),
        "created_by_email": t.get("created_by_email", ""),
        "created_by_full_name": t.get("created_by_full_name", ""),
        "assigned_to": assigned,
        "tasklist_name": tasklist.get("name", ""),
        "tasklist_id": tasklist.get("id", ""),
        "duration": t.get("duration", ""),
        "duration_type": t.get("duration_type", "days"),
        "work": t.get("work", ""),
        "billingtype": t.get("billingtype", "None"),
        "isparent": t.get("isparent", False),
        "subtasks": t.get("subtasks", False),
        "is_reminder_set": t.get("is_reminder_set", False),
        "is_recurrence_set": t.get("is_recurrence_set", False),
        "log_hours_billable": log_hours.get("billable_hours", "0.0"),
        "log_hours_non_billable": log_hours.get("non_billable_hours", "0.0"),
        "followers": followers,
        "milestone_id": t.get("milestone_id", ""),
        "added_via": t.get("added_via", ""),
        "link_web": t.get("link", {}).get("web", {}).get("url", ""),
    }


def _norm_member(m: dict) -> dict:
    return {
        "id": str(m.get("id", "")),
        "zpuid": str(m.get("zpuid", "")),
        "name": m.get("name", ""),
        "email": m.get("email", ""),
        "role": m.get("role", ""),
        "portal_role_name": m.get("portal_role_name", ""),
        "portal_profile_name": m.get("portal_profile_name", ""),
        "active": m.get("active", True),
        "profile_type": m.get("profile_type", ""),
        "is_resource": m.get("is_resource", False),
        "chat_access": m.get("chat_access", False),
    }


# ─────────────────────────────────────────────────────────────
# Public API functions
# ─────────────────────────────────────────────────────────────

async def fetch_projects(token: str) -> list[dict]:
    portal_id = await _get_portal_id(token)
    data = await _get(f"{BASE}/portal/{portal_id}/projects/", token)
    raw = data.get("projects", [])
    return [_norm_project(p) for p in raw]


async def fetch_project_detail(project_id: str, token: str) -> dict:
    portal_id = await _get_portal_id(token)
    data = await _get(f"{BASE}/portal/{portal_id}/projects/{project_id}/", token)
    raw = data.get("projects", [])
    if not raw:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")
    return _norm_project(raw[0])


async def fetch_tasks(project_id: str, token: str) -> list[dict]:
    portal_id = await _get_portal_id(token)
    data = await _get(f"{BASE}/portal/{portal_id}/projects/{project_id}/tasks/", token)
    raw = data.get("tasks", [])
    return [_norm_task(t) for t in raw]


async def fetch_task_detail(project_id: str, task_id: str, token: str) -> dict:
    portal_id = await _get_portal_id(token)
    data = await _get(
        f"{BASE}/portal/{portal_id}/projects/{project_id}/tasks/{task_id}/", token
    )
    tasks = data.get("tasks", [])
    raw = tasks[0] if tasks else data
    if not raw:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return _norm_task(raw)


async def fetch_project_members(project_id: str, token: str) -> list[dict]:
    portal_id = await _get_portal_id(token)
    data = await _get(f"{BASE}/portal/{portal_id}/projects/{project_id}/users/", token)
    raw = data.get("users", [])
    return [_norm_member(m) for m in raw]
