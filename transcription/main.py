"""
Local transcription server — runs on user's machine at localhost:8001.
Accepts MP3 uploads, runs Whisper + pyannote, returns formatted transcript.
Never deployed to Railway — local only.
"""

import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from transcription.logger import get_transcription_logger
from transcription.transcribe import get_pipeline, get_whisper, transcribe_audio

load_dotenv(Path(__file__).parent / ".env")

logger = get_transcription_logger("server")
request_logger = get_transcription_logger("requests")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [Transcription] Local transcription server starting on port 8001")
    get_whisper()
    get_pipeline()
    logger.info("✅ [Transcription] Models ready")
    yield


app = FastAPI(title="Call Tracker — Local Transcription Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def log_requests(request: Request, call_next):
    start = time.time()
    request_logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    request_logger.info(
        f"📤 {request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms)"
    )
    return response


app.add_middleware(BaseHTTPMiddleware, dispatch=log_requests)


@app.get("/health")
async def health():
    return {"status": "ok", "models": "loaded"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    ext = os.path.splitext(audio.filename or "")[1].lower()
    if ext != ".mp3":
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Only .mp3 is accepted.",
        )

    logger.info(f"🚀 [Transcription] Starting: {audio.filename}")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        transcript_text = transcribe_audio(tmp_path, audio.filename or "")
    finally:
        os.unlink(tmp_path)

    return {"transcript": transcript_text, "filename": audio.filename}
