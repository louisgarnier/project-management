"""
Local transcription server — runs on user's machine at localhost:8001.
Accepts MP3 uploads, runs Whisper + pyannote, returns formatted transcript.
Never deployed to Railway — local only.
"""

import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from transcription.logger import get_transcription_logger

load_dotenv()

logger = get_transcription_logger("server")
request_logger = get_transcription_logger("requests")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 [Transcription] Local transcription server starting on port 8001")
    yield


app = FastAPI(title="Call Tracker — Local Transcription Server", lifespan=lifespan)

# CORS open — browser (HTTPS Vercel) calls this HTTP localhost endpoint
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

# Models loaded once at startup — lazy init on first request if not pre-loaded
_whisper_model = None
_diarization_pipeline = None


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        logger.info("🔄 [Transcription] Loading Whisper medium model...")
        _whisper_model = whisper.load_model("medium")
        logger.info("✅ [Transcription] Whisper model loaded")
    return _whisper_model


def get_pipeline():
    global _diarization_pipeline
    if _diarization_pipeline is None:
        from pyannote.audio import Pipeline
        hf_token = os.getenv("HF_TOKEN")
        logger.info("🔄 [Transcription] Loading pyannote diarization pipeline...")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        logger.info("✅ [Transcription] Diarization pipeline loaded")
    return _diarization_pipeline


@app.get("/health")
async def health():
    return {"status": "ok", "models": "ready"}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    allowed = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    ext = os.path.splitext(audio.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(allowed)}",
        )

    import tempfile

    logger.info(f"🚀 [Transcription] Starting: {audio.filename}")

    # Save upload to temp file
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        transcript_text = _run_transcription(tmp_path, audio.filename or "")
    finally:
        os.unlink(tmp_path)

    return {"transcript": transcript_text, "filename": audio.filename}


def _run_transcription(audio_path: str, filename: str) -> str:
    """
    Replicates transcribe_watcher.py 100%:
    - Whisper medium model for ASR
    - pyannote speaker diarization
    - Merge: [MM:SS] SPEAKER_X: text per segment
    """
    model = get_whisper()
    pipeline = get_pipeline()

    logger.info(f"🔄 [Transcription] Whisper transcribing {filename}...")
    result = model.transcribe(audio_path, word_timestamps=False)
    segments = result.get("segments", [])
    logger.info(f"🔄 [Transcription] Whisper complete ({len(segments)} segments)")

    logger.info(f"🔄 [Transcription] Running diarization on {filename}...")
    diarization = pipeline(audio_path)
    logger.info("🔄 [Transcription] Diarization complete")

    # Build speaker turn list from diarization
    speaker_turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_turns.append((turn.start, turn.end, speaker))

    # Assign each Whisper segment to the speaker with most overlap
    lines = []
    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        text = seg["text"].strip()
        if not text:
            continue

        best_speaker = "SPEAKER_00"
        best_overlap = 0.0
        for t_start, t_end, speaker in speaker_turns:
            overlap = min(seg_end, t_end) - max(seg_start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker

        minutes = int(seg_start) // 60
        seconds = int(seg_start) % 60
        timestamp = f"[{minutes:02d}:{seconds:02d}]"
        lines.append(f"{timestamp} {best_speaker}: {text}")

    transcript_text = "\n".join(lines)
    logger.info(
        f"✅ [Transcription] Done: {len(lines)} lines, {len(transcript_text)} chars"
    )
    return transcript_text
