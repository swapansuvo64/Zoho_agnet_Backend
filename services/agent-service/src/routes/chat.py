import asyncio
import json
import uuid
import logging
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from src.controllers.jwt_handler import jwt_handler
from src.Config.redis import get_redis, get_value, delete_value
from src.Config.settings import settings

async def fetch_zoho_token_from_auth_service(user_id: str, access_token: str) -> str | None:
    """
    Calls the auth-service to fetch/refresh the Zoho access token.
    """
    try:
        url = f"{settings.AUTH_SERVICE_URL.rstrip('/')}/auth/zoho/token"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                token = data.get("zoho_access_token")
                if token:
                    logger.info(f"Successfully retrieved Zoho access token from auth-service for user_id={user_id}")
                    return token
            logger.warning(f"Auth-service returned status {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to call auth-service to get Zoho access token: {str(e)}")
    return None

import importlib
longterm_memory = importlib.import_module("src.memory.longterm-memory")
save_chat_message = longterm_memory.save_chat_message
load_chat_history = longterm_memory.load_chat_history
save_chat_summary = longterm_memory.save_chat_summary
load_chat_summary = longterm_memory.load_chat_summary
migrate_session_to_ltm = longterm_memory.migrate_session_to_ltm
vectorize_session_summary = longterm_memory.vectorize_session_summary
search_long_term_memory = longterm_memory.search_long_term_memory

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
    user_info = None
    zoho_access_token = None
    
    # Get the raw access token
    access_token = token or websocket.cookies.get("access_token")
    
    try:
        # Authenticate user
        user_id = await get_ws_user_id(websocket, token)
        logger.info(f"WebSocket client authenticated successfully. user_id={user_id}, session_id={session_id}")
        
        # Query user details from Supabase SQL table 'users'
        try:
            db = await get_db()
            user_res = await db.table("users").select("name, email").eq("id", user_id).execute()
            if user_res.data:
                user_info = user_res.data[0]
                logger.info(f"Successfully loaded user info from SQL: name='{user_info.get('name')}', email='{user_info.get('email')}'")
        except Exception as db_err:
            logger.error(f"Failed to query user details from database: {str(db_err)}")

        # Fetch Zoho access token from auth-service
        try:
            zoho_access_token = await fetch_zoho_token_from_auth_service(user_id, access_token)
            if zoho_access_token:
                logger.info(f"Zoho access token fetched from auth-service for user_id={user_id}")
            else:
                logger.warning(f"No Zoho access token found from auth-service for user_id={user_id}. Zoho tools will be unavailable.")
        except Exception as zoho_err:
            logger.error(f"Failed to fetch Zoho access token: {str(zoho_err)}")

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

    # Seed running summary in Redis cache from database if present
    try:
        past_summary = await load_chat_summary(session_id)
        if past_summary:
            redis = await get_redis()
            redis_key = f"summary:{session_id}"
            exists = await redis.exists(redis_key)
            if not exists:
                summary_data = {
                    "summary": past_summary.get("summary", "No summary yet."),
                    "projects_mentioned": past_summary.get("projects_mentioned", []),
                    "tasks_mentioned": past_summary.get("tasks_mentioned", []),
                    "actions_taken": past_summary.get("actions_taken", []),
                    "total_turns": past_summary.get("total_turns", 0)
                }
                # Set 24 hours TTL for the summary cache in Redis
                await redis.set(redis_key, json.dumps(summary_data), ex=86400)
                logger.info(f"Seeded summary cache for session {session_id} from database.")
    except Exception as e:
        logger.error(f"Error seeding running summary cache on connection: {str(e)}")

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
            new_messages.append({
                "role": "user",
                "message": message_text,
                "tool_name": None,
                "tool_args": None,
                "tool_result": None
            })
            
            # 2. Retrieve semantic context from short-term memory using cosine + Jaccard re-ranking
            stm_context = await short_term_memory.get_context(session_id, message_text, limit=3)
            
            # Retrieve semantic context from long-term memory (LTM)
            ltm_context = await search_long_term_memory(user_id, message_text, limit=3)
            
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

            # Fetch / refresh Zoho access token dynamically from auth-service for every turn
            try:
                zoho_access_token = await fetch_zoho_token_from_auth_service(user_id, access_token)
            except Exception as zoho_err:
                logger.error(f"Failed to fetch Zoho access token during chat turn: {str(zoho_err)}")

            # 4. Route through MainAgent brain → query_agent / action_agent / conversational LLM
            full_response = ""
            await websocket.send_json({"type": "start"})
            tool_info = {"tool_name": None, "tool_args": None, "tool_result": None}
            async for chunk in main_agent.get_response_stream(
                query=message_text,
                session_id=session_id,
                stm_context=stm_context,
                ltm_context=ltm_context,
                summary=summary,
                user_info=user_info,
                zoho_access_token=zoho_access_token,
                tool_info=tool_info
            ):
                full_response += chunk
                await websocket.send_json({"type": "chunk", "text": chunk})
            await websocket.send_json({"type": "done"})
            
            assistant_msg_id = str(uuid.uuid4())
            
            # 5. Add assistant response to short-term memory cache
            await short_term_memory.add_message(session_id, assistant_msg_id, "assistant", full_response)
            
            # Accumulate in local list for bulk persist on disconnect
            new_messages.append({
                "role": "assistant",
                "message": full_response,
                "tool_name": tool_info.get("tool_name"),
                "tool_args": tool_info.get("tool_args"),
                "tool_result": tool_info.get("tool_result")
            })
            
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
                        "message": msg["message"],
                        "tool_name": msg.get("tool_name"),
                        "tool_args": msg.get("tool_args"),
                        "tool_result": msg.get("tool_result")
                    }
                    for msg in new_messages
                ]
                await db.table("chat_history").insert(payload).execute()
                logger.info(f"Bulk persisted {len(new_messages)} new messages to Supabase chat_history for session {session_id}")
            except Exception as bulk_err:
                logger.error(f"Error bulk persisting chat history to database: {str(bulk_err)}")

        # Persist active summary from Redis into Supabase database, migrate to long-term memory, and clear memory caches
        if user_id:
            try:
                redis = await get_redis()
                redis_key = f"summary:{session_id}"
                cached_summary = await get_value(redis, redis_key)
                if cached_summary:
                    summary_text = ""
                    try:
                        summary_obj = json.loads(cached_summary)
                        summary_text = summary_obj.get("summary", "")
                        await save_chat_summary(
                            user_id=user_id,
                            session_id=session_id,
                            summary=summary_text,
                            projects_mentioned=summary_obj.get("projects_mentioned", []),
                            tasks_mentioned=summary_obj.get("tasks_mentioned", []),
                            actions_taken=summary_obj.get("actions_taken", []),
                            total_turns=summary_obj.get("total_turns", 0)
                        )
                        logger.info(f"Saved final chat summary to long-term database for session {session_id}")
                    except Exception as summary_save_err:
                        logger.error(f"Error parsing/saving final summary: {str(summary_save_err)}")

                    # Migrate the short-term memory vectors to long-term memory vector store before clearing STM
                    try:
                        await migrate_session_to_ltm(user_id, session_id)
                    except Exception as migration_err:
                        logger.error(f"Error migrating STM to LTM: {str(migration_err)}")

                    # Vectorize the final session summary and save to LTM Chroma
                    if summary_text:
                        try:
                            await vectorize_session_summary(user_id, session_id, summary_text)
                        except Exception as sum_vec_err:
                            logger.error(f"Error vectorizing session summary for LTM: {str(sum_vec_err)}")
                    
                    # Clean up Redis summary
                    await delete_value(redis, redis_key)
            except Exception as redis_err:
                logger.error(f"Error processing long-term memory updates during disconnect: {str(redis_err)}")
        
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

@router.get("/sessions")
async def get_user_sessions(request: Request, token: str = Query(None), db = Depends(get_db)):
    """Return all chat sessions (with summaries) for the authenticated user."""
    try:
        # Support both cookie auth and ?token= query param
        access_token = token or request.cookies.get("access_token")
        if not access_token:
            return JSONResponse(content={"error": "Missing access token"}, status_code=401)
        
        payload = jwt_handler.verify_token(access_token, "access")
        user_id = payload.get("sub")
        if not user_id:
            return JSONResponse(content={"error": "Invalid token"}, status_code=401)
        
        res = await db.table("chat_summaries")\
            .select("session_id, summary, total_turns, created_at, updated_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        return JSONResponse(content={"sessions": res.data or []})
    except Exception as e:
        logger.error(f"Error fetching user sessions: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
