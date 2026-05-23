import httpx
import logging
from sentence_transformers import SentenceTransformer
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

# Global reference for SentenceTransformer model
fallback_model = None

def load_fallback_model():
    global fallback_model
    if fallback_model is None:
        logger.info("Loading fallback SentenceTransformer model (all-MiniLM-L6-v2) eagerly...")
        try:
            fallback_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer model: {str(e)}")
            raise e

async def get_embedding(text: str) -> list[float]:
    google_key = settings.GOOGLE_API_KEY
    if not google_key:
        logger.warning("GOOGLE_API_KEY not found in settings. Using SentenceTransformer fallback embedding.")
        return get_fallback_embedding(text)
        
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
                logger.warning(f"Google embedding API failed with status {resp.status_code}. Response: {resp.text[:200]}. Using SentenceTransformer fallback embedding.")
    except Exception as e:
        logger.warning(f"Error fetching embedding from Google: {str(e)}. Using SentenceTransformer fallback embedding.")
    
    return get_fallback_embedding(text)

def get_fallback_embedding(text: str) -> list[float]:
    global fallback_model
    if fallback_model is None:
        load_fallback_model()
        
    # Generate 384-dimensional embedding using the loaded SentenceTransformer model
    emb = fallback_model.encode(text).tolist()
    
    # Pad to 3072 dimensions to match Gemini gemini-embedding-2 dimension and prevent Chroma collection dimension mismatch errors
    if len(emb) < 3072:
        emb = emb + [0.0] * (3072 - len(emb))
    return emb
