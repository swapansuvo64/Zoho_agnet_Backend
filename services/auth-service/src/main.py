from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.Config.settings import settings
from src.Config.database import init_db, get_db
from src.Config.redis import init_redis, get_redis
from src.controllers.token_manager import token_manager
from src.utils.cron import CronJob
from src.routes.auth import router as auth_router

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("auth-service")

cron_job: CronJob = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cron_job
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

    # 3. Instantiate and start Cron Job for Zoho access token rotation (only if db and redis are active)
    if db is not None and redis is not None:
        logger.info("Starting background cron job...")
        cron_job = CronJob(token_manager, redis, db)
        cron_job.start()
    else:
        logger.warning("Background cron job not started due to failed Supabase or Redis connection.")

    logger.info("Auth service ready")
    yield

    # Lifespan Shutdown
    logger.info("Shutting down auth-service...")
    if cron_job:
        cron_job.stop()
    logger.info("Auth-service shutdown completed.")

app = FastAPI(
    title="Zoho Agent - Auth Service",
    description="Authentication Service for Zoho Agent",
    version="0.1.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Authentication Routing
app.include_router(auth_router, prefix="/auth", tags=["auth"])

@app.get("/")
async def root():
    return {
        "service": "auth-service",
        "status": "healthy",
        "port": 8001
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
