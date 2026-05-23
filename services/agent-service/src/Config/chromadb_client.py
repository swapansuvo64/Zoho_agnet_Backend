import logging
import chromadb
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

# Create singleton HTTP client connected to the ChromaDB Docker service
try:
    chroma_client = chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=int(settings.CHROMA_PORT)
    )
    logger.info(f"Initialized ChromaDB HttpClient pointing to {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
except Exception as e:
    logger.error(f"Failed to initialize ChromaDB HttpClient: {str(e)}")
    # Fallback to an empty or default Client if instantiation fails during import time
    chroma_client = None
