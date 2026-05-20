# Story 4.7 — Replace Transcription Engine with MLX Whisper

**Epic:** EPIC-4 — Transcript Stage
**Status:** `done`
**Depends on:** None (independent of 4.5/4.6, but should be done before 4.5 to avoid rework)
**Priority:** High — current engine (openai-whisper + pyannote) is too slow for production use

---

## Goal
Replace the transcription server's engine (`openai-whisper` + `pyannote`) with `mlx-whisper` — the same engine used in `Claude/PM/`. This brings transcription speed in the app to the same level as the standalone PM tool. Speaker diarization and timestamps are dropped entirely; output is clean raw text matching the PM folder's output format.

## Context
The PM folder (`/Users/louisgarnier/Claude/PM/`) uses `mlx-community/whisper-large-v3-turbo` via `mlx-whisper 0.4.3`, running on Apple Silicon's Neural Engine. It transcribes MP3s in seconds. The current app uses `openai-whisper` on CPU + `pyannote` for diarization — far slower.

The model weights (~800MB) are already cached at `~/.cache/huggingface/` from the PM setup. No re-download needed.

## What Changes

| Component | Before | After |
|---|---|---|
| Engine | openai-whisper (CPU) + pyannote | mlx-whisper (Apple Silicon Neural Engine) |
| Output format | `[00:00] SPEAKER_00: text` | `raw text, no labels` |
| Speaker labels | Yes (via pyannote) | No |
| Timestamps | Yes | No |
| HF_TOKEN | Required | Not needed |
| WAV conversion | Required (ffmpeg) | Not needed (mlx handles MP3) |
| Model load time | ~30s (whisper) + ~15s (pyannote) | ~5s |
| venv size | ~4GB | ~500MB |

## Acceptance Criteria

### transcription/requirements.txt
- [x] `openai-whisper`, `pyannote.audio`, `torchaudio` removed
- [x] `mlx-whisper==0.4.3` added
- [x] `torch` kept (mlx-whisper depends on it for some ops)
- [x] `python-multipart`, `fastapi`, `uvicorn`, `python-dotenv`, `httpx`, `pytest` kept

### transcription/transcribe.py
- [x] `get_whisper()` replaced with `preload_model()` — calls `ModelHolder.get_model()` to warm up MLX model at startup
- [x] `get_pipeline()` removed entirely
- [x] `_mp3_to_wav()` removed entirely
- [x] `transcribe_audio(audio_path, filename) → str` rewritten:
  - Calls `mlx_whisper.transcribe(audio_path, path_or_hf_repo="mlx-community/whisper-large-v3-turbo")`
  - Returns `result["text"].strip()`
  - No speaker detection, no timestamp formatting
- [x] All logging retained (`📥 Starting`, `✅ Done`, `❌ Failed`)

### transcription/main.py
- [x] Lifespan calls `preload_model()` only (no `get_pipeline()`)
- [x] `load_dotenv()` call removed (no env vars needed)
- [x] `Path` import removed
- [x] Startup log updated: `"🚀 [Transcription] Local transcription server starting on port 8001"`
- [x] Health endpoint still returns `{"status": "ok", "models": "loaded"}`
- [x] `/transcribe` endpoint unchanged (still accepts MP3, returns `{"transcript": str, "filename": str}`)

### transcription/.env / .env.example
- [x] `transcription/.env.example` updated — `HF_TOKEN` line removed, comment: `# No environment variables required for transcription`
- [x] `transcription/.env` deleted (no longer needed)

### run_transcription.sh
- [x] Venv check updated: checks `import mlx_whisper` instead of `import whisper`
- [x] On first run: deletes old venv if it exists, creates fresh venv, installs new requirements

### Venv
- [x] Old venv at `transcription/.venv` deleted
- [x] New venv built with `mlx-whisper==0.4.3` and dependencies
- [x] `mlx_whisper.transcribe` verified working with a real MP3

### Tests — transcription/tests/
- [x] `test_transcribe.py` rewritten for mlx-whisper API
- [x] `test_health.py` updated — lifespan mock updated for `preload_model`
- [x] All 6 transcription tests pass

### Integration test
- [x] Server started via `./run_transcription.sh`
- [x] Real MP3 transcribed — clean raw text output confirmed
- [x] Transcription speed comparable to PM folder

## Tasks
- [x] Delete `transcription/.venv`
- [x] Update `transcription/requirements.txt`
- [x] Rewrite `transcription/transcribe.py`
- [x] Update `transcription/main.py`
- [x] Update `run_transcription.sh` — venv check + fresh build
- [x] Update `transcription/.env.example`, delete `transcription/.env`
- [x] Rewrite `transcription/tests/test_transcribe.py`
- [x] Update `transcription/tests/test_health.py`
- [x] Rebuild venv and verify all 6 tests pass
- [x] Integration test with real MP3
- [x] Update `workflow/ERRORS.md` — ERR-003 follow-up added
- [x] Update `docs/project/config/codebase.md`
