import json
import logging
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from src.Config.model import llm
from src.Config.redis import get_redis, get_value, set_value
from src.agnets.prompt import get_summary_prompt

logger = logging.getLogger("agent-service")

async def call_summary_llm(messages: list) -> str:
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
            
    try:
        resp = await llm.ainvoke(lc_messages)
        return resp.content
    except Exception as e:
        logger.error(f"Error calling Gemini LLM via LangChain in summary agent: {str(e)}")
        raise e

async def update_running_summary(session_id: str, new_user_msg: str, new_agent_msg: str):
    try:
        redis = await get_redis()
        redis_key = f"summary:{session_id}"
        
        # 1. Fetch current cached summary
        cached = await get_value(redis, redis_key)
        if cached:
            try:
                summary_data = json.loads(cached)
            except Exception:
                summary_data = None
        else:
            summary_data = None

        if not summary_data:
            summary_data = {
                "summary": "No summary yet.",
                "user_facts": [],
                "people_mentioned": [],
                "projects_mentioned": [],
                "tasks_mentioned": [],
                "actions_taken": [],
                "decisions_made": [],
                "topics_discussed": [],
                "total_turns": 0
            }

        # Increment turns
        summary_data["total_turns"] = summary_data.get("total_turns", 0) + 1

        # 2. Build prompt for Gemini LLM
        prompt = get_summary_prompt(summary_data, new_user_msg, new_agent_msg)

        messages = [
            {"role": "user", "content": prompt}
        ]
        
        # 3. Call Gemini using ChatGoogleGenerativeAI via LangChain
        response_text = await call_summary_llm(messages)
        
        # Clean response if markdown blocks are included
        response_text = response_text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            updated_state = json.loads(response_text)
            # Ensure required keys exist
            required_keys = [
                "summary", "user_facts", "people_mentioned", 
                "projects_mentioned", "tasks_mentioned", 
                "actions_taken", "decisions_made", "topics_discussed"
            ]
            for key in required_keys:
                if key not in updated_state:
                    updated_state[key] = summary_data.get(key)
        except Exception as parse_err:
            logger.warning(f"Failed to parse summary LLM response as JSON: {response_text}. Error: {str(parse_err)}")
            # Fallback: keep previous state but update turns
            updated_state = summary_data

        # Merge turns count back
        updated_state["total_turns"] = summary_data["total_turns"]
        
        # 4. Save back to Redis
        await set_value(redis, redis_key, json.dumps(updated_state), 86400) # 24h cache TTL
        logger.info(f"Updated running summary for session {session_id}: {updated_state['summary']}")
    except Exception as e:
        logger.error(f"Error in background summary update for session {session_id}: {str(e)}")
