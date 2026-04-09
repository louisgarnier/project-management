# Story 4.1 — Local Transcription Server

**Epic:** EPIC-4 — Transcript Stage
**Maps to plan:** Slice 4
**Maps to PRD:** US-02, FR-02, NG-03
**Status:** `done`

---

## Goal
The local FastAPI transcription server accepts an MP3, runs Whisper + pyannote (exact port of `transcribe_watcher.py`), and returns the formatted transcript. The server runs on the user's machine at `localhost:8001`.

## Acceptance Criteria
- [x] `GET /health` returns `{"status":"ok","models":"loaded"}` once Whisper + pyannote are loaded
- [x] `POST /transcribe` accepts `multipart/form-data` with an `audio` file field
- [x] Output format matches `transcribe_watcher.py`: `[MM:SS] SPEAKER_X: text` per line
- [x] Whisper model: `medium`
- [x] Pyannote pipeline: `pyannote/speaker-diarization-3.1`
- [x] Models loaded once at startup (not per request)
- [x] CORS set to `allow_origins=["*"]` (browser calls from HTTPS Vercel)
- [x] All transcription steps logged via `transcription/logger.py`: start, whisper done, diarization done, merge done, output length
- [x] Error: unsupported file type → 422 with clear message
- [x] `run_transcription.sh` script starts the server with one command

## Tasks
- [x] Port `transcribe_watcher.py` to `transcription/transcribe.py` (see reference at `/Users/louisgarnier/Claude/PM/transcribe_watcher.py`)
- [x] Refactor into functions: `get_whisper()`, `get_pipeline()`, `transcribe_audio(path, filename) → str`
- [x] Create `transcription/main.py` — FastAPI with startup model loading, CORS, `/health`, `/transcribe`
- [x] Create `run_transcription.sh` in project root
- [x] Write test: `transcription/tests/test_transcribe.py` with a short MP3 fixture

## Reference
- Source to replicate: `/Users/louisgarnier/Claude/PM/transcribe_watcher.py`
- Design spec: `/Users/louisgarnier/Claude/PM/docs/superpowers/specs/2026-04-03-transcription-watcher-design.md`

## Dev Tests
- `transcription/tests/test_transcribe.py`:
  - `GET /health` → 200, `{"status":"ok"}`
  - `POST /transcribe` with a valid short MP3 → 200, response contains `[00:` (timestamp format)
  - `POST /transcribe` with a `.txt` file → 422
