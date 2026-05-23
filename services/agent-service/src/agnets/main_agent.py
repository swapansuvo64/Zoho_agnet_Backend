import logging
from langchain_core.messages import SystemMessage, HumanMessage
from src.Config.model import llm
from src.agnets.prompt import get_main_agent_system_prompt

logger = logging.getLogger("agent-service")

class MainAgent:
    async def get_response_stream(self, query: str, stm_context: list[str], ltm_context: list[dict], summary: str, user_info: dict = None):
        stm_context_str = "\n".join(f"- {c}" for c in stm_context) if stm_context else "No relevant current session context found."
        
        ltm_items = []
        for item in ltm_context:
            t = item.get("text", "")
            meta = item.get("metadata", {}) or {}
            m_type = meta.get("type", "message")
            role = meta.get("role", "")
            session_id = meta.get("session_id", "")
            if m_type == "summary":
                ltm_items.append(f"- [Past Session Summary (Session: {session_id})]: {t}")
            else:
                prefix = f" ({role})" if role else ""
                ltm_items.append(f"- [Past Message{prefix} (Session: {session_id})]: {t}")
        
        ltm_context_str = "\n".join(ltm_items) if ltm_items else "No relevant historical past session memory found."
        
        system_prompt = get_main_agent_system_prompt(summary, stm_context_str, ltm_context_str, user_info)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]

        try:
            async for chunk in llm.astream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            logger.error(f"Exception while streaming from ChatGroq via LangChain: {str(e)}")
            yield f"Error in LLM streaming client: {str(e)}"

main_agent = MainAgent()
