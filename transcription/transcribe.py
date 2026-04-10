import mlx.core as mx
import mlx_whisper
from mlx_whisper.transcribe import ModelHolder

from transcription.logger import get_transcription_logger

logger = get_transcription_logger("transcribe")

MODEL = "mlx-community/whisper-large-v3-turbo"


def preload_model() -> None:
    """Warm up the MLX Whisper model at server startup."""
    logger.info("🔄 [Transcription] Loading MLX Whisper model...")
    ModelHolder.get_model(MODEL, mx.float16)
    logger.info("✅ [Transcription] MLX Whisper model loaded")


def transcribe_audio(audio_path: str, filename: str) -> str:
    """Transcribe audio_path with mlx-whisper. Returns raw text, no labels or timestamps."""
    logger.info(f"📥 [Transcription] Starting: {filename}")
    try:
        result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=MODEL)
        text = result["text"].strip()
        logger.info(f"✅ [Transcription] Done: {filename} ({len(text)} chars)")
        return text
    except Exception as e:
        logger.error(f"❌ [Transcription] Failed: {filename}: {e}")
        raise
