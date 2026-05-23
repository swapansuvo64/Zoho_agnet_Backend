import logging
from src.Config.database import get_db

logger = logging.getLogger("agent-service")

async def save_chat_message(user_id: str, session_id: str, role: str, message: str) -> dict | None:
    try:
        db = await get_db()
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "role": role,
            "message": message
        }
        res = await db.table("chat_history").insert(payload).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"Error saving chat message to DB: {str(e)}")
    return None

async def load_chat_history(session_id: str) -> list[dict]:
    try:
        db = await get_db()
        res = await db.table("chat_history")\
            .select("*")\
            .eq("session_id", session_id)\
            .order("created_at", desc=False)\
            .execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error loading chat history from DB: {str(e)}")
        return []

async def save_chat_summary(
    user_id: str,
    session_id: str,
    summary: str,
    projects_mentioned: list[str] = None,
    tasks_mentioned: list[str] = None,
    actions_taken: list[str] = None,
    total_turns: int = 0
) -> dict | None:
    try:
        db = await get_db()
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "summary": summary,
            "projects_mentioned": projects_mentioned or [],
            "tasks_mentioned": tasks_mentioned or [],
            "actions_taken": actions_taken or [],
            "total_turns": total_turns
        }
        res = await db.table("chat_summaries").upsert(payload, on_conflict="session_id").execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"Error saving chat summary to DB: {str(e)}")
    return None

async def load_chat_summary(session_id: str) -> dict | None:
    try:
        db = await get_db()
        res = await db.table("chat_summaries")\
            .select("*")\
            .eq("session_id", session_id)\
            .execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.error(f"Error loading chat summary from DB: {str(e)}")
    return None

