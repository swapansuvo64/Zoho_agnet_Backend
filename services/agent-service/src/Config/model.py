import logging
from langchain_groq import ChatGroq
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

logger.info("Initializing LangChain ChatGroq models...")

# Primary LLM instance
llm = ChatGroq(
    api_key=settings.GROQ_API_KEY,
    model=settings.MODEL,
    temperature=0.7
)

# Fallback LLM instance
fallback_llm = ChatGroq(
    api_key=settings.GROQ_API_KEY,
    model=settings.FALL_BACK_MODEL,
    temperature=0.7
)

logger.info("LangChain ChatGroq models initialized successfully.")
