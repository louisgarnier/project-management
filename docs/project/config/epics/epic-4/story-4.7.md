# Story 4.7 — Replace Transcription Engine with MLX Whisper

**Epic:** EPIC-4 — Transcript Stage
**Status:** `pending`
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
- [ ] `openai-whisper`, `pyannote.audio`, `torchaudio` removed
- [ ] `mlx-whisper==0.4.3` added
- [ ] `torch` kept (mlx-whisper depends on it for some ops)
- [ ] `python-multipart`, `fastapi`, `uvicorn`, `python-dotenv`, `httpx`, `pytest` kept

### transcription/transcribe.py
- [ ] `get_whisper()` replaced with `preload_model()` — calls `ModelHolder.get_model()` to warm up MLX model at startup
- [ ] `get_pipeline()` removed entirely
- [ ] `_mp3_to_wav()` removed entirely
- [ ] `transcribe_audio(audio_path, filename) → str` rewritten:
  - Calls `mlx_whisper.transcribe(audio_path, path_or_hf_repo="mlx-community/whisper-large-v3-turbo")`
  - Returns `result["text"].strip()`
  - No speaker detection, no timestamp formatting
- [ ] All logging retained (`📥 Starting`, `✅ Done`, `❌ Failed`)

### transcription/main.py
- [ ] Lifespan calls `preload_model()` only (no `get_pipeline()`)
- [ ] `load_dotenv()` call removed (no env vars needed)
- [ ] `Path` import removed
- [ ] Startup log updated: `"🚀 [Transcription] Local transcription server starting on port 8001"`
- [ ] Health endpoint still returns `{"status": "ok", "models": "loaded"}`
- [ ] `/transcribe` endpoint unchanged (still accepts MP3, returns `{"transcript": str, "filename": str}`)

### transcription/.env / .env.example
- [ ] `transcription/.env.example` updated — `HF_TOKEN` line removed, comment added: `# No environment variables required for transcription`
- [ ] `transcription/.env` deleted (no longer needed)

### run_transcription.sh
- [ ] Venv check updated: checks `import mlx_whisper` instead of `import whisper`
- [ ] On first run: deletes old venv if it exists (to avoid stale torch/pyannote packages), creates fresh venv, installs new requirements

### Venv
- [ ] Old venv at `transcription/.venv` deleted
- [ ] New venv built with `mlx-whisper==0.4.3` and dependencies
- [ ] `mlx_whisper.transcribe` verified working with a real MP3

### Tests — transcription/tests/
- [ ] `test_transcribe.py` rewritten for mlx-whisper API:
  - Mock `mlx_whisper.transcribe` (not `whisper.load_model`)
  - `test_transcribe_audio_returns_text()` — mocks mlx call, verifies `.strip()` applied
  - `test_transcribe_audio_logs_filename()` — verifies filename logged
  - `test_transcribe_api_mp3_only()` — POST non-mp3 → 422
  - `test_transcribe_api_happy_path()` — POST mp3 → `{"transcript": "...", "filename": "..."}`
- [ ] `test_health.py` updated — lifespan mock updated for `preload_model` (no pipeline)
- [ ] All 6 transcription tests pass

### Integration test
- [ ] Start server via `./run_transcription.sh`
- [ ] POST a real MP3 to `http://localhost:8001/transcribe`
- [ ] Response contains `{"transcript": "<non-empty text>", "filename": "..."}`
- [ ] Transcript is clean raw text (no `[00:00]`, no `SPEAKER_00:`)
- [ ] Transcription completes at speed comparable to PM folder

## Tasks
- [ ] Delete `transcription/.venv`
- [ ] Update `transcription/requirements.txt`
- [ ] Rewrite `transcription/transcribe.py`
- [ ] Update `transcription/main.py`
- [ ] Update `run_transcription.sh` — venv check + fresh build
- [ ] Update `transcription/.env.example`, delete `transcription/.env`
- [ ] Rewrite `transcription/tests/test_transcribe.py`
- [ ] Update `transcription/tests/test_health.py`
- [ ] Rebuild venv and verify all 6 tests pass
- [ ] Integration test with real MP3
- [ ] Update `workflow/ERRORS.md` — close ERR-003 (venv issues now resolved by fresh build)
- [ ] Update `docs/project/config/codebase.md`
