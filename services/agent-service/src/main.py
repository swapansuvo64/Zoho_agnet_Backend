import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Zoho Agent Backend",
    description="FastAPI Backend for Zoho Agent",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "message": "Zoho Agent Backend API is running successfully!",
        "environment": {
            "has_zoho_client_id": bool(os.getenv("ZOHO_Client_ID")),
            "has_zoho_client_secret": bool(os.getenv("ZOHO_Client_Secret"))
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
