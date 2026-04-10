import os
import subprocess
import tempfile
from transcription.logger import get_transcription_logger

logger = get_transcription_logger("transcribe")

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
        if not hf_token:
            raise RuntimeError("HF_TOKEN environment variable is not set")
        logger.info("🔄 [Transcription] Loading pyannote diarization pipeline...")
        try:
            _diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                token=hf_token,
            )
        except Exception as e:
            logger.error(f"❌ [Transcription] Failed to load pyannote pipeline: {e}")
            raise
        logger.info("✅ [Transcription] Diarization pipeline loaded")
    return _diarization_pipeline


def _mp3_to_wav(mp3_path: str) -> str:
    """Convert MP3 to 16kHz mono WAV. Returns temp WAV path (caller must delete)."""
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path],
        check=True,
        capture_output=True,
    )
    return wav_path


def transcribe_audio(audio_path: str, filename: str) -> str:
    """Run Whisper + pyannote on audio_path. Returns [MM:SS] SPEAKER_X: text per line."""
    model = get_whisper()
    pipeline = get_pipeline()

    logger.info(f"📥 [Transcription] Starting: {filename}")

    wav_path = _mp3_to_wav(audio_path)
    try:
        result = model.transcribe(wav_path, word_timestamps=False)
        segments = result.get("segments", [])
        logger.info(f"✅ [Transcription] Whisper done: {len(segments)} segments")

        diarization_output = pipeline(wav_path)
        logger.info("✅ [Transcription] Diarization done")
    finally:
        os.unlink(wav_path)

    speaker_turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in diarization_output.speaker_diarization.itertracks(yield_label=True)
    ]

    lines = []
    for seg in segments:
        seg_start, seg_end = seg["start"], seg["end"]
        text = seg["text"].strip()
        if not text:
            continue

        best_speaker = "SPEAKER_0"
        best_overlap = 0.0
        for t_start, t_end, speaker in speaker_turns:
            overlap = min(seg_end, t_end) - max(seg_start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker

        mm, ss = int(seg_start) // 60, int(seg_start) % 60
        lines.append(f"[{mm:02d}:{ss:02d}] {best_speaker}: {text}")

    output = "\n".join(lines)
    logger.info(f"✅ [Transcription] Merge done: {len(lines)} lines, {len(output)} chars")
    return output
