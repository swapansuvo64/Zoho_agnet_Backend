import logging
from langchain_core.messages import SystemMessage, HumanMessage
from src.Config.model import llm
from src.agnets.prompt import get_main_agent_system_prompt

logger = logging.getLogger("agent-service")

class MainAgent:
    async def get_response_stream(self, query: str, context: list[str], summary: str):
        context_str = "\n".join(f"- {c}" for c in context) if context else "No relevant context found."
        system_prompt = get_main_agent_system_prompt(summary, context_str)

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
