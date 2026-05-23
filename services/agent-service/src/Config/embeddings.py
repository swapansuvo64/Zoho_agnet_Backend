import httpx
import logging
import asyncio
from langchain_core.embeddings import Embeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

# Custom LangChain Embeddings class for Google Gemini embedding models
class GoogleGeminiEmbeddings(Embeddings):
    async def aembed_query(self, text: str) -> list[float]:
        google_key = settings.GOOGLE_API_KEY
        if not google_key:
            logger.warning("GOOGLE_API_KEY not found in settings. Using SentenceTransformer fallback embedding.")
            return await aget_fallback_embedding(text)
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={google_key}"
        payload = {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": text}]}
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=5.0)
                if resp.status_code == 200:
                    return resp.json()["embedding"]["values"]
                else:
                    logger.warning(f"Google embedding API failed with status {resp.status_code}. Response: {resp.text[:200]}. Using fallback.")
        except Exception as e:
            logger.warning(f"Error fetching embedding from Google: {str(e)}. Using fallback.")
        
        return await aget_fallback_embedding(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        tasks = [self.aembed_query(text) for text in texts]
        return await asyncio.gather(*tasks)

    def embed_query(self, text: str) -> list[float]:
        # Sync fallback implementation
        google_key = settings.GOOGLE_API_KEY
        if not google_key:
            return get_fallback_embedding(text)
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={google_key}"
        payload = {
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": text}]}
        }
        try:
            with httpx.Client() as client:
                resp = client.post(url, json=payload, timeout=5.0)
                if resp.status_code == 200:
                    return resp.json()["embedding"]["values"]
        except Exception as e:
            logger.warning(f"Sync embedding request failed: {str(e)}. Using fallback.")
        
        return get_fallback_embedding(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


# Global fallback model using LangChain's HuggingFaceEmbeddings
fallback_embeddings = None

def load_fallback_model():
    global fallback_embeddings
    if fallback_embeddings is None:
        logger.info("Loading fallback HuggingFaceEmbeddings eagerly...")
        try:
            fallback_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            logger.info("HuggingFaceEmbeddings model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load HuggingFaceEmbeddings model: {str(e)}")
            raise e

# Instantiate LangChain-compatible Gemini Embeddings
gemini_embeddings = GoogleGeminiEmbeddings()

async def aget_fallback_embedding(text: str) -> list[float]:
    global fallback_embeddings
    if fallback_embeddings is None:
        load_fallback_model()
    # Retrieve 384 dimensional embedding using HuggingFaceEmbeddings
    emb = await fallback_embeddings.aembed_query(text)
    # Pad to 3072 dimensions to match Gemini gemini-embedding-2 size
    if len(emb) < 3072:
        emb = emb + [0.0] * (3072 - len(emb))
    return emb

def get_fallback_embedding(text: str) -> list[float]:
    global fallback_embeddings
    if fallback_embeddings is None:
        load_fallback_model()
    # Retrieve 384 dimensional embedding using HuggingFaceEmbeddings
    emb = fallback_embeddings.embed_query(text)
    # Pad to 3072 dimensions to match Gemini gemini-embedding-2 size
    if len(emb) < 3072:
        emb = emb + [0.0] * (3072 - len(emb))
    return emb

# Keep simple helper export for memory modules
async def get_embedding(text: str) -> list[float]:
    return await gemini_embeddings.aembed_query(text)
