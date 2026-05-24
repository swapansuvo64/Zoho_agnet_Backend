import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

logger.info("Initializing LangChain ChatGoogleGenerativeAI models...")

# Primary LLM instance (Gemini 1.5 Pro - highly intelligent, excellent tool execution)
llm = ChatGoogleGenerativeAI(
    google_api_key=settings.GOOGLE_API_KEY,
    model="gemini-1.5-pro",
    temperature=0.7
)

# Fallback LLM instance (Gemini 1.5 Flash - fast and highly capable fallback)
fallback_llm = ChatGoogleGenerativeAI(
    google_api_key=settings.GOOGLE_API_KEY,
    model="gemini-1.5-flash",
    temperature=0.7
)

logger.info("LangChain ChatGoogleGenerativeAI models initialized successfully.")
