from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.Config.settings import settings
from src.Config.database import init_db, get_db
from src.Config.redis import init_redis, get_redis

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("agent-service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing services on startup...")
    
    # 1. Initialize & Test Supabase client
    db = None
    logger.info("Connecting to Supabase...")
    try:
        db = await init_db()
    except Exception as e:
        logger.warning(f"Failed to connect to Supabase: {str(e)}. Proceeding anyway...")
    
    # 2. Initialize & Test Redis client
    redis = None
    logger.info("Connecting to Redis...")
    try:
        redis = await init_redis()
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {str(e)}. Proceeding anyway...")

    logger.info("Agent service ready")
    yield

    # Lifespan Shutdown
    logger.info("Shutting down agent-service...")
    logger.info("Agent-service shutdown completed.")

app = FastAPI(
    title="Zoho Agent Backend",
    description="FastAPI Backend for Zoho Agent",
    version="0.1.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from src.routes.chat import router as chat_router
app.include_router(chat_router)


@app.get("/")
async def root():
    return {
        "service": "agent-service",
        "status": "healthy",
        "port": 8000,
        "environment": {
            "has_zoho_client_id": bool(settings.ZOHO_CLIENT_ID),
            "has_zoho_client_secret": bool(settings.ZOHO_CLIENT_SECRET)
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

