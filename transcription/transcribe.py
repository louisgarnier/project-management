import mlx.core as mx
import mlx_whisper
import numpy as np
from mlx_whisper.transcribe import ModelHolder

from transcription.logger import get_transcription_logger

logger = get_transcription_logger("transcribe")

MODEL = "mlx-community/whisper-large-v3-turbo"


def preload_model() -> None:
    """Load model weights and run a dummy inference to compile Metal shaders.

    Without the warm-up, the first real transcription pays a ~15-20s JIT cost
    for Metal shader compilation. Running a silent dummy call at startup amortises
    that cost so every user request gets consistent latency.
    """
    logger.info("🔄 [Transcription] Loading MLX Whisper model...")
    ModelHolder.get_model(MODEL, mx.float16)
    logger.info("🔥 [Transcription] Warming up Metal shaders...")
    # 0.5s of silence at 16 kHz — enough to trigger full Metal pipeline init
    dummy = np.zeros(8000, dtype=np.float32)
    mlx_whisper.transcribe(dummy, path_or_hf_repo=MODEL)
    logger.info("✅ [Transcription] MLX Whisper model loaded and warmed up")


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
