import asyncio
import json
import uuid
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, Depends, Query, status
from fastapi.responses import JSONResponse
from src.controllers.jwt_handler import jwt_handler
from src.Config.redis import get_redis, get_value, delete_value

import importlib
longterm_memory = importlib.import_module("src.memory.longterm-memory")
save_chat_message = longterm_memory.save_chat_message
load_chat_history = longterm_memory.load_chat_history
save_chat_summary = longterm_memory.save_chat_summary

shortterm_memory_mod = importlib.import_module("src.memory.shortterm-memory")
short_term_memory = shortterm_memory_mod.short_term_memory

from src.agnets.chat_summary_agnet import update_running_summary
from src.agnets.main_agent import main_agent
from src.Config.database import get_db

logger = logging.getLogger("agent-service")
router = APIRouter(prefix="/chat", tags=["chat"])

async def get_ws_user_id(websocket: WebSocket, token: str = None) -> str:
    access_token = token or websocket.cookies.get("access_token")
    if not access_token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token.")
    try:
        payload = jwt_handler.verify_token(access_token, "access")
        user_id = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token: missing sub.")
        return user_id
    except Exception as e:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=f"Token verification failed: {str(e)}")

@router.websocket("/ws/{session_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(None)
):
    # Accept WS connection
    await websocket.accept()
    
    user_id = None
    new_messages = []
    
    try:
        # Authenticate user
        user_id = await get_ws_user_id(websocket, token)
        logger.info(f"WebSocket client authenticated successfully. user_id={user_id}, session_id={session_id}")
    except WebSocketException as wse:
        logger.warning(f"WebSocket auth failed: {wse.reason}")
        await websocket.send_json({"type": "error", "message": wse.reason})
        await websocket.close(code=wse.code)
        return
    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
        await websocket.send_json({"type": "error", "message": "Authentication error."})
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # Seed vector DB memory with past chat history from database
    try:
        past_messages = await load_chat_history(session_id)
        await short_term_memory.seed_session(session_id, past_messages)
        logger.info(f"Seeded short-term memory for session {session_id} with {len(past_messages)} past messages.")
    except Exception as e:
        logger.error(f"Error seeding short-term memory on connection: {str(e)}")

    # Main interaction loop
    try:
        while True:
            # Wait for client input message
            message_text = await websocket.receive_text()
            if not message_text.strip():
                continue
            
            logger.info(f"Received message from client {user_id} in session {session_id}: {message_text[:100]}")
            
            user_msg_id = str(uuid.uuid4())
            
            # 1. Add message to short-term memory cache (Redis list + Chroma vector store)
            await short_term_memory.add_message(session_id, user_msg_id, "user", message_text)
            
            # Accumulate in local list for bulk persist on disconnect
            new_messages.append({"role": "user", "message": message_text})
            
            # 2. Retrieve semantic context from short-term memory using cosine + Jaccard re-ranking
            context = await short_term_memory.get_context(session_id, message_text, limit=3)
            
            # 3. Fetch the running summary from Redis
            redis = await get_redis()
            redis_key = f"summary:{session_id}"
            cached_summary = await get_value(redis, redis_key)
            summary = "No summary yet."
            if cached_summary:
                try:
                    summary_obj = json.loads(cached_summary)
                    summary = summary_obj.get("summary", "No summary yet.")
                except Exception:
                    pass

            # 4. Stream LLM response chunk-by-chunk to the WebSocket
            full_response = ""
            await websocket.send_json({"type": "start"})
            async for chunk in main_agent.get_response_stream(message_text, context, summary):
                full_response += chunk
                await websocket.send_json({"type": "chunk", "text": chunk})
            await websocket.send_json({"type": "done"})
            
            assistant_msg_id = str(uuid.uuid4())
            
            # 5. Add assistant response to short-term memory cache
            await short_term_memory.add_message(session_id, assistant_msg_id, "assistant", full_response)
            
            # Accumulate in local list for bulk persist on disconnect
            new_messages.append({"role": "assistant", "message": full_response})
            
            # 6. Trigger background summary worker to update running summary in Redis
            asyncio.create_task(update_running_summary(session_id, message_text, full_response))

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {user_id} disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket session error: {str(e)}")
    finally:
        # Chat session ended: Persist new messages in bulk to Supabase database
        if user_id and new_messages:
            try:
                db = await get_db()
                payload = [
                    {
                        "user_id": user_id,
                        "session_id": session_id,
                        "role": msg["role"],
                        "message": msg["message"]
                    }
                    for msg in new_messages
                ]
                await db.table("chat_history").insert(payload).execute()
                logger.info(f"Bulk persisted {len(new_messages)} new messages to Supabase chat_history for session {session_id}")
            except Exception as bulk_err:
                logger.error(f"Error bulk persisting chat history to database: {str(bulk_err)}")

        # Persist active summary from Redis into Supabase database, and clear memory caches
        if user_id:
            try:
                redis = await get_redis()
                redis_key = f"summary:{session_id}"
                cached_summary = await get_value(redis, redis_key)
                if cached_summary:
                    try:
                        summary_obj = json.loads(cached_summary)
                        await save_chat_summary(
                            user_id=user_id,
                            session_id=session_id,
                            summary=summary_obj.get("summary", ""),
                            projects_mentioned=summary_obj.get("projects_mentioned", []),
                            tasks_mentioned=summary_obj.get("tasks_mentioned", []),
                            actions_taken=summary_obj.get("actions_taken", []),
                            total_turns=summary_obj.get("total_turns", 0)
                        )
                        logger.info(f"Saved final chat summary to long-term database for session {session_id}")
                    except Exception as summary_save_err:
                        logger.error(f"Error parsing/saving final summary: {str(summary_save_err)}")
                    
                    # Clean up Redis summary
                    await delete_value(redis, redis_key)
            except Exception as redis_err:
                logger.error(f"Error checking summary during disconnect: {str(redis_err)}")
        
        # Clean up temporary Redis cache and Chroma memory collection
        try:
            await short_term_memory.clear_session(session_id)
        except Exception as chroma_err:
            logger.error(f"Error cleaning up short-term memory: {str(chroma_err)}")

@router.get("/history/{session_id}")
async def get_session_history(session_id: str, db = Depends(get_db)):
    try:
        res = await db.table("chat_history")\
            .select("*")\
            .eq("session_id", session_id)\
            .order("created_at", desc=False)\
            .execute()
        return JSONResponse(content={"history": res.data or []})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@router.get("/summary/{session_id}")
async def get_session_summary(session_id: str, db = Depends(get_db)):
    try:
        res = await db.table("chat_summaries")\
            .select("*")\
            .eq("session_id", session_id)\
            .execute()
        if res.data:
            return JSONResponse(content={"summary": res.data[0]})
        return JSONResponse(content={"summary": None})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
