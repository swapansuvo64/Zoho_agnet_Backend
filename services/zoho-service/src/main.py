import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("zoho-service")

from src.routes import projects, tasks

app = FastAPI(
    title="Zoho Agent — Zoho Service",
    description=(
        "REST API that wraps Zoho Projects endpoints for the frontend. "
        "The agent embeds resource IDs (project_id, task_id) in its chat summaries. "
        "The frontend calls these endpoints to fetch full detail for popup display."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the Vite dev server and the agent frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# Register routers
app.include_router(projects.router)
app.include_router(tasks.router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "zoho-service",
        "status": "healthy",
        "port": 8003,
        "endpoints": [
            "GET /zoho/projects",
            "GET /zoho/projects/{project_id}",
            "GET /zoho/projects/{project_id}/members",
            "GET /zoho/projects/{project_id}/tasks",
            "GET /zoho/projects/{project_id}/tasks/{task_id}",
        ],
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "OK"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8003, reload=True)
