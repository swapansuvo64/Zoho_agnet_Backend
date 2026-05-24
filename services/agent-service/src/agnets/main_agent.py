import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from src.Config.model import llm
from src.Config.redis import get_redis, get_value
from src.agnets.prompt import get_main_agent_system_prompt, CLASSIFY_INTENT_PROMPT

logger = logging.getLogger("agent-service")

# Confirmation keywords (user approving or declining a pending action)
CONFIRM_KEYWORDS = {"yes", "confirm", "proceed", "go ahead", "do it", "approve", "execute"}
DECLINE_KEYWORDS  = {"no", "cancel", "abort", "stop", "decline", "reject", "don't", "nope"}

class MainAgent:
    """
    The central brain of the Zoho Projects AI Agent.

    Responsibilities (strictly separated):
      1. Detect Human-in-the-Loop confirmations and route to ActionAgent.execute_pending_action().
      2. Classify intent as 'query', 'action', or 'conversational'.
      3. Delegate 'query' intents to QueryAgent (read-only, no confirmation needed).
      4. Delegate 'action' intents to ActionAgent.initiate_action() → shows confirmation card.
      5. Handle 'conversational' intents directly with memory context.

    Does NOT implement any Zoho API calls or tool logic itself.
    """

    async def _classify_intent(self, query: str) -> str:
        """
        Uses LLM to classify the user message into one of three intents.
        Returns: 'query' | 'action' | 'conversational'
        """
        messages = [
            SystemMessage(content=CLASSIFY_INTENT_PROMPT),
            HumanMessage(content=query)
        ]
        try:
            resp = await llm.ainvoke(messages)
            intent = resp.content.strip().lower()
            if intent not in ("query", "action", "conversational"):
                intent = "conversational"
            return intent
        except Exception as e:
            logger.error(f"Intent classification failed: {str(e)}")
            return "conversational"

    async def get_response_stream(
        self,
        query: str,
        session_id: str,
        stm_context: list[str],
        ltm_context: list[dict],
        summary: str,
        user_info: dict = None,
        zoho_access_token: str = None,
        tool_info: dict = None
    ):
        """
        Entry point for every user message. Yields string chunks to stream over WebSocket.
        """
        import asyncio
        # ── Step 1: Check if this is a Human-in-the-Loop confirmation/cancellation ──
        redis = await get_redis()
        pending_key = f"pending_action:{session_id}"
        pending_multi_key = f"pending_actions:{session_id}"
        has_pending = await redis.exists(pending_key)
        has_multi_pending = await redis.exists(pending_multi_key)

        if has_multi_pending:
            normalized = query.strip().lower().rstrip(".")
            if normalized in CONFIRM_KEYWORDS:
                if not zoho_access_token:
                    yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                    return
                
                yield "💭 *Just give me a moment... processing your confirmation and executing batch updates on Zoho Projects in parallel.*\n\n"
                await asyncio.sleep(0.4)
                
                from src.agnets.orchestrator_agent import orchestrator_agent
                response = await orchestrator_agent.execute_pending_actions(
                    session_id=session_id,
                    access_token=zoho_access_token,
                    approved=True
                )
                yield response
                return
            elif normalized in DECLINE_KEYWORDS:
                await redis.delete(pending_multi_key)
                yield "❌ **Action Aborted.** The pending multi-task write operations have been canceled cleanly."
                return
            else:
                yield (
                    "⚠️ You have a **pending multi-task action** awaiting your confirmation.\n\n"
                    "Please reply **\"Yes\"** to proceed or **\"No\"** to cancel before continuing."
                )
                return

        elif has_pending:
            normalized = query.strip().lower().rstrip(".")
            if normalized in CONFIRM_KEYWORDS:
                if not zoho_access_token:
                    yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                    return
                
                yield "💭 *Just give me a moment... processing your confirmation and writing to Zoho Projects.*\n\n"
                await asyncio.sleep(0.4)
                
                from src.agnets.action_agent import action_graph
                initial_state = {
                    "operation": "execute_pending",
                    "query": None,
                    "session_id": session_id,
                    "access_token": zoho_access_token,
                    "approved": True,
                    "action": None,
                    "args": None,
                    "clarification_needed": None,
                    "tool_result": None,
                    "response": None,
                    "error": None
                }
                
                final_response = ""
                async for event in action_graph.astream(initial_state):
                    if "load_and_run" in event:
                        state = event["load_and_run"]
                        if state.get("action"):
                            yield f"⚙️ *Using Tool:* `{state['action']}`\n\n"
                            await asyncio.sleep(0.4)
                        if tool_info is not None:
                            tool_info["tool_name"] = state.get("action")
                            tool_info["tool_args"] = state.get("args")
                            tool_info["tool_result"] = state.get("tool_result")
                    elif "explain_action" in event:
                        state = event["explain_action"]
                        if state.get("response"):
                            final_response = state["response"]
                        if tool_info is not None:
                            if state.get("action"):
                                tool_info["tool_name"] = state.get("action")
                            if state.get("args"):
                                tool_info["tool_args"] = state.get("args")
                            if state.get("tool_result"):
                                tool_info["tool_result"] = state.get("tool_result")
                
                if final_response:
                    yield final_response
                return
                
            elif normalized in DECLINE_KEYWORDS:
                if not zoho_access_token:
                    yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                    return
                
                yield "💭 *Just give me a moment... canceling your pending write action cleanly.*\n\n"
                await asyncio.sleep(0.4)
                
                from src.agnets.action_agent import action_graph
                initial_state = {
                    "operation": "execute_pending",
                    "query": None,
                    "session_id": session_id,
                    "access_token": zoho_access_token,
                    "approved": False,
                    "action": None,
                    "args": None,
                    "clarification_needed": None,
                    "tool_result": None,
                    "response": None,
                    "error": None
                }
                
                final_response = ""
                async for event in action_graph.astream(initial_state):
                    if "load_and_run" in event:
                        state = event["load_and_run"]
                        if state.get("response"):
                            final_response = state["response"]
                
                if final_response:
                    yield final_response
                return
            else:
                # User said something unrelated while a pending action is waiting
                yield (
                    "⚠️ You have a **pending action** awaiting your confirmation.\n\n"
                    "Please reply **\"Yes\"** to proceed or **\"No\"** to cancel before continuing."
                )
                return

        # ── Step 2: Classify intent ──
        intent = await self._classify_intent(query)
        logger.info(f"MainAgent classified intent='{intent}' for query: {query[:80]}")

        # ── Step 3: Route based on intent ──

        if intent == "query":
            if not zoho_access_token:
                yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                return
            
            yield "💭 *Analyzing your request...*\n\n"
            await asyncio.sleep(0.3)
            
            from src.agnets.query_agent import query_graph
            initial_state = {
                "query": query,
                "access_token": zoho_access_token,
                "tool": None,
                "args": None,
                "clarification_needed": None,
                "tool_result": None,
                "response": None,
                "error": None,
                "stm_context": stm_context,
                "ltm_context": ltm_context,   # ← cross-session vector DB recall
                "summary": summary
            }
            
            final_response = ""
            async for event in query_graph.astream(initial_state):
                if "route_query" in event:
                    state = event["route_query"]
                    if state.get("tool") and not state.get("clarification_needed"):
                        yield f"⚙️ *Using Tool:* `{state['tool']}`\n\n"
                        await asyncio.sleep(0.2)
                        yield "📡 *Fetching data from Zoho Projects...*\n\n"
                        await asyncio.sleep(0.2)
                elif "execute_tool" in event:
                    state = event["execute_tool"]
                    if tool_info is not None:
                        tool_info["tool_name"] = state.get("tool")
                        tool_info["tool_args"] = state.get("args")
                        tool_info["tool_result"] = state.get("tool_result")
                    yield "✍️ *Formatting your results...*\n\n"
                    await asyncio.sleep(0.2)
                elif "explain" in event:
                    state = event["explain"]
                    if state.get("response"):
                        final_response = state["response"]
                    if tool_info is not None:
                        if state.get("tool"):
                            tool_info["tool_name"] = state.get("tool")
                        if state.get("args"):
                            tool_info["tool_args"] = state.get("args")
                        if state.get("tool_result"):
                            tool_info["tool_result"] = state.get("tool_result")
            
            if final_response:
                yield final_response
            return

        if intent == "action":
            if not zoho_access_token:
                yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                return
            
            yield "💭 *Understanding your request...*\n\n"
            await asyncio.sleep(0.3)
            
            from src.agnets.action_agent import action_graph
            initial_state = {
                "operation": "initiate",
                "query": query,
                "session_id": session_id,
                "access_token": None,
                "approved": None,
                "action": None,
                "args": None,
                "clarification_needed": None,
                "tool_result": None,
                "response": None,
                "error": None,
                "stm_context": stm_context,
                "ltm_context": ltm_context,   # ← cross-session vector DB recall
                "summary": summary
            }
            
            final_response = ""
            async for event in action_graph.astream(initial_state):
                if "parse_action" in event:
                    state = event["parse_action"]
                    if state.get("action") and not state.get("clarification_needed"):
                        yield f"⚙️ *Using Tool:* `{state['action']}`\n\n"
                        await asyncio.sleep(0.2)
                        yield "🔐 *Preparing confirmation for your approval...*\n\n"
                        await asyncio.sleep(0.2)
                    if tool_info is not None:
                        tool_info["tool_name"] = state.get("action")
                        tool_info["tool_args"] = state.get("args")
                        tool_info["tool_result"] = None
                elif "confirmation_prompt" in event:
                    state = event["confirmation_prompt"]
                    if state.get("response"):
                        final_response = state["response"]
                    if tool_info is not None:
                        if state.get("action"):
                            tool_info["tool_name"] = state.get("action")
                        if state.get("args"):
                            tool_info["tool_args"] = state.get("args")
            
            if final_response:
                yield final_response
            return

        if intent == "orchestration":
            if not zoho_access_token:
                yield "⚠️ I couldn't retrieve your Zoho access token. Please reconnect or re-authenticate."
                return
            
            yield "💭 *Analyzing your multi-step request...*\n\n"
            await asyncio.sleep(0.3)
            yield "🔀 *Planning parallel agent execution...*\n\n"
            await asyncio.sleep(0.2)
            
            from src.agnets.orchestrator_agent import orchestrator_agent
            response = await orchestrator_agent.initiate_orchestration(
                query=query,
                session_id=session_id,
                access_token=zoho_access_token,
                stm_context=stm_context,
                summary=summary
            )
            yield response
            return

        # ── Step 4: Conversational — stream directly with memory context ──
        # No status chunk here — the frontend ThinkingIndicator (bouncing dots) already covers the wait.

        stm_context_str = (
            "\n".join(f"- {c}" for c in stm_context)
            if stm_context
            else "No relevant current session context found."
        )

        ltm_items = []
        for item in ltm_context:
            t    = item.get("text", "")
            meta = item.get("metadata", {}) or {}
            m_type     = meta.get("type", "message")
            role       = meta.get("role", "")
            sid        = meta.get("session_id", "")
            if m_type == "summary":
                ltm_items.append(f"- [Past Session Summary (Session: {sid})]: {t}")
            else:
                prefix = f" ({role})" if role else ""
                ltm_items.append(f"- [Past Message{prefix} (Session: {sid})]: {t}")

        ltm_context_str = (
            "\n".join(ltm_items)
            if ltm_items
            else "No relevant historical past session memory found."
        )

        import importlib
        shortterm_memory_mod = importlib.import_module("src.memory.shortterm-memory")
        short_term_memory = shortterm_memory_mod.short_term_memory
        
        try:
            history = await short_term_memory.get_temporary_history(session_id)
            past_msgs = history
            if past_msgs and past_msgs[-1].get("message") == query:
                past_msgs = past_msgs[:-1]
            last_5 = past_msgs[-5:]
            chrono_items = []
            for msg in last_5:
                role = "User" if msg.get("role") == "user" else "Assistant"
                text = msg.get("message", "")
                chrono_items.append(f"{role}: {text}")
            chrono_context_str = "\n".join(chrono_items) if chrono_items else "No preceding messages in the current session."
        except Exception as e:
            logger.error(f"Error fetching chronological history: {str(e)}")
            chrono_context_str = "No preceding messages in the current session."

        system_prompt = get_main_agent_system_prompt(
            summary, stm_context_str, ltm_context_str, user_info, chrono_context_str
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"Exception while streaming from LLM: {str(e)}")
            yield f"Error in LLM streaming client: {str(e)}"

main_agent = MainAgent()
