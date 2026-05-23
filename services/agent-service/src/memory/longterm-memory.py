import logging
from src.Config.database import get_db
from src.Config.embeddings import get_embedding
from src.memory.vectordb import ltm_memory, chroma_memory

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

async def migrate_session_to_ltm(user_id: str, session_id: str):
    """
    Migrates all vectorized messages of the session from short-term memory (Chroma STM)
    to long-term memory (Chroma LTM ltm_{user_id}) using their pre-calculated embeddings.
    """
    try:
        stm_messages = chroma_memory.get_all_messages(session_id)
        if not stm_messages:
            logger.info(f"No messages found in short-term memory for session {session_id} to migrate to LTM.")
            return
        
        logger.info(f"Migrating {len(stm_messages)} vectorized messages from STM to LTM for user {user_id}, session {session_id}")
        for msg in stm_messages:
            msg_id = msg["id"]
            text = msg["text"]
            embedding = msg["embedding"]
            role = msg["metadata"].get("role", "user")
            
            if embedding:
                await ltm_memory.upsert_message(
                    user_id=user_id,
                    msg_id=msg_id,
                    session_id=session_id,
                    role=role,
                    text=text,
                    embedding=embedding
                )
        logger.info(f"Successfully migrated session {session_id} messages to LTM for user {user_id}")
    except Exception as e:
        logger.error(f"Error migrating session to LTM: {str(e)}")

async def vectorize_session_summary(user_id: str, session_id: str, summary_text: str):
    """
    Embeds and saves the final session summary into long-term memory (Chroma LTM).
    """
    try:
        if not summary_text or summary_text.strip() in ("", "No summary yet."):
            return
        logger.info(f"Vectorizing session summary for session {session_id} and saving to LTM...")
        embedding = await get_embedding(summary_text)
        await ltm_memory.upsert_summary(
            user_id=user_id,
            session_id=session_id,
            summary_text=summary_text,
            embedding=embedding
        )
        logger.info(f"Successfully saved session summary to LTM for user {user_id}")
    except Exception as e:
        logger.error(f"Error vectorizing session summary to LTM: {str(e)}")

async def search_long_term_memory(user_id: str, query_text: str, limit: int = 5) -> list[dict]:
    """
    Performs semantic search across the user's entire historical long-term memory (Chroma LTM).
    """
    try:
        search_query = query_text if query_text.strip() else "past topics summary projects tasks and key conversations"
        query_embedding = await get_embedding(search_query)
        results = await ltm_memory.search(user_id, query_embedding, limit=limit)
        return results
    except Exception as e:
        logger.error(f"Error searching long term memory: {str(e)}")
        return []

