"""
Local transcription server — runs on user's machine at localhost:8001.
Accepts MP3 uploads, runs mlx-whisper on Apple Silicon, returns raw transcript text.
Never deployed to Railway — local only.
"""

import asyncio
import os
import tempfile
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from transcription.logger import get_transcription_logger
from transcription.transcribe import preload_model, transcribe_audio

logger = get_transcription_logger("server")
request_logger = get_transcription_logger("requests")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [Transcription] Local transcription server starting on port 8001")
    preload_model()
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
        # Run blocking mlx-whisper inference in a thread pool so the event loop
        # stays free to handle /health checks during transcription.
        loop = asyncio.get_event_loop()
        transcript_text = await loop.run_in_executor(
            None, transcribe_audio, tmp_path, audio.filename or ""
        )
    finally:
        os.unlink(tmp_path)

    return {"transcript": transcript_text, "filename": audio.filename}
