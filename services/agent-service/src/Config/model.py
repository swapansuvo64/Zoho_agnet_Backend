import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

logger.info("Initializing LangChain ChatGoogleGenerativeAI models...")

# Primary LLM instance (Gemini - configurable via .env settings.MODEL)
llm = ChatGoogleGenerativeAI(
    google_api_key=settings.GOOGLE_API_KEY,
    model=settings.MODEL,
    temperature=0.7
)

# Fallback LLM instance (Gemini - configurable via .env settings.FALL_BACK_MODEL)
fallback_llm = ChatGoogleGenerativeAI(
    google_api_key=settings.GOOGLE_API_KEY,
    model=settings.FALL_BACK_MODEL,
    temperature=0.7
)

logger.info(f"LangChain ChatGoogleGenerativeAI models initialized successfully with MODEL={settings.MODEL}.")
