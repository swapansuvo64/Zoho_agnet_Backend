import hashlib
import httpx
import logging
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

async def get_embedding(text: str) -> list[float]:
    google_key = settings.GOOGLE_API_KEY
    if not google_key:
        logger.warning("GOOGLE_API_KEY not found in settings. Using fallback embedding.")
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
                logger.warning(f"Google embedding API failed with status {resp.status_code}. Response: {resp.text[:200]}. Using fallback embedding.")
    except Exception as e:
        logger.warning(f"Error fetching embedding from Google: {str(e)}. Using fallback embedding.")
    
    return get_fallback_embedding(text)

def get_fallback_embedding(text: str) -> list[float]:
    # Deterministic vector based on hashing string characters (dimension 3072)
    h = hashlib.sha256(text.encode('utf-8')).digest()
    # Generate 3072 values
    vec = []
    for i in range(3072):
        val = ((h[i % 32] + i) % 256) / 255.0 - 0.5
        vec.append(val)
    return vec
