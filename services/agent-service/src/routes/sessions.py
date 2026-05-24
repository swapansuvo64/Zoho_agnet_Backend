import logging
import importlib
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import JSONResponse

from src.controllers.jwt_handler import jwt_handler
from src.Config.database import get_db
from src.Config.redis import get_redis, delete_value

logger = logging.getLogger("agent-service")

router = APIRouter(prefix="/sessions", tags=["sessions"])

# ── Memory modules ────────────────────────────────────────────────────────────
shortterm_memory_mod = importlib.import_module("src.memory.shortterm-memory")
short_term_memory = shortterm_memory_mod.short_term_memory

from src.memory.vectordb import ltm_memory


def _get_user(request: Request, token: str = None) -> str | None:
    """Extract and verify access token; return user_id or None."""
    access_token = token or request.cookies.get("access_token")
    if not access_token:
        return None
    try:
        payload = jwt_handler.verify_token(access_token, "access")
        return payload.get("sub")
    except Exception:
        return None


# ── DELETE /sessions/{session_id} ─────────────────────────────────────────────
@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    token: str = Query(None),
    db=Depends(get_db),
):
    """
    Permanently deletes a chat session:
    1. Removes all rows from `chat_history`
    2. Removes row from `chat_summaries`
    3. Clears the Redis running-summary cache key
    4. Clears the short-term Chroma collection (STM)
    5. Removes all LTM Chroma vectors tagged with this session_id
    """
    user_id = _get_user(request, token)
    if not user_id:
        return JSONResponse(content={"error": "Unauthorized"}, status_code=401)

    errors: list[str] = []

    # 1. Delete chat_history rows
    try:
        await db.table("chat_history") \
            .delete() \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()
        logger.info(f"Deleted chat_history rows for session {session_id}")
    except Exception as e:
        msg = f"chat_history delete failed: {e}"
        logger.error(msg)
        errors.append(msg)

    # 2. Delete chat_summaries row
    try:
        await db.table("chat_summaries") \
            .delete() \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()
        logger.info(f"Deleted chat_summaries row for session {session_id}")
    except Exception as e:
        msg = f"chat_summaries delete failed: {e}"
        logger.error(msg)
        errors.append(msg)

    # 3. Clear Redis running-summary cache
    try:
        redis = await get_redis()
        await delete_value(redis, f"summary:{session_id}")
        # Also clean up any pending action keys for this session
        await delete_value(redis, f"pending_action:{session_id}")
        await delete_value(redis, f"pending_actions:{session_id}")
        logger.info(f"Cleared Redis keys for session {session_id}")
    except Exception as e:
        msg = f"Redis clear failed: {e}"
        logger.error(msg)
        errors.append(msg)

    # 4. Clear short-term Chroma STM collection
    try:
        await short_term_memory.clear_session(session_id)
        logger.info(f"Cleared STM Chroma collection for session {session_id}")
    except Exception as e:
        msg = f"STM clear failed: {e}"
        logger.error(msg)
        errors.append(msg)

    # 5. Remove LTM Chroma vectors for this session
    try:
        ltm_memory.delete_session_from_ltm(user_id, session_id)
        logger.info(f"Deleted LTM vectors for session {session_id}")
    except Exception as e:
        msg = f"LTM delete failed: {e}"
        logger.error(msg)
        errors.append(msg)

    if errors:
        return JSONResponse(
            content={"success": False, "deleted": False, "errors": errors},
            status_code=207,
        )

    return JSONResponse(content={"success": True, "deleted": True, "session_id": session_id})


# ── PATCH /sessions/{session_id}/save ─────────────────────────────────────────
@router.patch("/{session_id}/save")
async def toggle_save_session(
    session_id: str,
    request: Request,
    token: str = Query(None),
    db=Depends(get_db),
):
    """
    Toggles the `is_saved` boolean on the chat_summaries row for a session.
    If the row doesn't exist yet (fresh session with no summary), creates a stub.
    Returns the new is_saved value.
    """
    user_id = _get_user(request, token)
    if not user_id:
        return JSONResponse(content={"error": "Unauthorized"}, status_code=401)

    try:
        # Read current value
        res = await db.table("chat_summaries") \
            .select("id, is_saved") \
            .eq("session_id", session_id) \
            .eq("user_id", user_id) \
            .execute()

        if res.data:
            current = res.data[0].get("is_saved", False)
            new_value = not current
            await db.table("chat_summaries") \
                .update({"is_saved": new_value}) \
                .eq("session_id", session_id) \
                .eq("user_id", user_id) \
                .execute()
        else:
            # No summary row yet — create a stub with is_saved=True
            new_value = True
            await db.table("chat_summaries").insert({
                "user_id": user_id,
                "session_id": session_id,
                "summary": "",
                "is_saved": True,
                "total_turns": 0,
            }).execute()

        logger.info(f"Set is_saved={new_value} for session {session_id}")
        return JSONResponse(content={"success": True, "session_id": session_id, "is_saved": new_value})

    except Exception as e:
        logger.error(f"Error toggling is_saved for session {session_id}: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
