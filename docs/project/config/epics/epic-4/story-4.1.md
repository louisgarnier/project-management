# Story 4.1 — Local Transcription Server

**Epic:** EPIC-4 — Transcript Stage
**Maps to plan:** Slice 4
**Maps to PRD:** US-02, FR-02, NG-03
**Status:** `pending`

---

## Goal
The local FastAPI transcription server accepts an MP3, runs Whisper + pyannote (exact port of `transcribe_watcher.py`), and returns the formatted transcript. The server runs on the user's machine at `localhost:8001`.

## Acceptance Criteria
- [ ] `GET /health` returns `{"status":"ok","models":"loaded"}` once Whisper + pyannote are loaded
- [ ] `POST /transcribe` accepts `multipart/form-data` with an `audio` file field
- [ ] Output format matches `transcribe_watcher.py`: `[MM:SS] SPEAKER_X: text` per line
- [ ] Whisper model: `medium`
- [ ] Pyannote pipeline: `pyannote/speaker-diarization-3.1`
- [ ] Models loaded once at startup (not per request)
- [ ] CORS set to `allow_origins=["*"]` (browser calls from HTTPS Vercel)
- [ ] All transcription steps logged via `transcription/logger.py`: start, whisper done, diarization done, merge done, output length
- [ ] Error: unsupported file type → 422 with clear message
- [ ] `run_transcription.sh` script starts the server with one command

## Tasks
- [ ] Port `transcribe_watcher.py` to `transcription/transcribe.py` (see reference at `/Users/louisgarnier/Claude/PM/transcribe_watcher.py`)
- [ ] Refactor into functions: `get_whisper()`, `get_pipeline()`, `transcribe_audio(path, filename) → str`
- [ ] Create `transcription/main.py` — FastAPI with startup model loading, CORS, `/health`, `/transcribe`
- [ ] Create `run_transcription.sh` in project root
- [ ] Write test: `transcription/tests/test_transcribe.py` with a short MP3 fixture

## Reference
- Source to replicate: `/Users/louisgarnier/Claude/PM/transcribe_watcher.py`
- Design spec: `/Users/louisgarnier/Claude/PM/docs/superpowers/specs/2026-04-03-transcription-watcher-design.md`

## Dev Tests
- `transcription/tests/test_transcribe.py`:
  - `GET /health` → 200, `{"status":"ok"}`
  - `POST /transcribe` with a valid short MP3 → 200, response contains `[00:` (timestamp format)
  - `POST /transcribe` with a `.txt` file → 422
