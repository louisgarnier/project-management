import os
from contextlib import asynccontextmanager

from backend.middleware.logging_middleware import log_requests
from backend.routers import artifact_types, artifacts, calls, files, projects
from backend.utils.logger import get_logger
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

logger = get_logger("startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [Railway] Call Tracker API starting")
    yield


app = FastAPI(title="Call Tracker API", lifespan=lifespan)

# CORS — allow Vercel frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging middleware — outermost so every request is captured
app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests)

app.include_router(projects.router)
app.include_router(calls.router)
app.include_router(files.router)
app.include_router(artifact_types.router)
app.include_router(artifacts.router)


@app.get("/health")
async def health():
    from backend.utils.logger import db_logger

    db_status = "not_configured"

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if supabase_url and supabase_key:
        try:
            from backend.database.supabase_client import get_client

            client = get_client()
            client.table("projects").select("id").limit(1).execute()
            db_status = "connected"
            db_logger.info("✅ [DB] Health check passed")
        except Exception as e:
            db_status = "error"
            db_logger.error(f"❌ [DB] Health check failed: {e}")

    return {"status": "ok", "db": db_status}
