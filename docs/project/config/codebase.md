# Codebase Map — Call Tracker
> Updated after every story. Read this before touching any existing module.
> Last updated: EPIC-4 / Story 4.1

---

## Module Index

```
backend/
├── main.py                        → FastAPI entry point, router registration (EPIC-1 / Story 1.1)
├── database.py                    → Supabase client factory (EPIC-1 / Story 1.3)
├── logger.py                      → Backend logger (EPIC-1 / Story 1.2)
├── routers/
│   ├── projects.py                → GET/POST/DELETE /api/projects (EPIC-2 / Story 2.1)
│   └── calls.py                   → GET/POST /api/projects/{id}/calls, PATCH /api/calls/{id}/stage (EPIC-3 / Story 3.1)
└── tests/
    ├── test_projects.py           → 5 tests for projects API (EPIC-2 / Story 2.1)
    └── test_calls.py              → 9 tests for calls API (EPIC-3 / Story 3.1)

frontend/
├── app/
│   ├── layout.tsx                 → Root layout: TopNav + Sidebar + main (EPIC-2 / Story 2.3)
│   ├── page.tsx                   → Landing: "select a project" (EPIC-2 / Story 2.3)
│   └── projects/[id]/
│       ├── page.tsx               → Redirects to /board (EPIC-2 / Story 2.3)
│       ├── board/page.tsx         → Kanban board (live calls) (EPIC-3 / Story 3.2)
│       ├── topics/page.tsx        → Placeholder (EPIC-2 / Story 2.3)
│       ├── history/page.tsx       → Placeholder (EPIC-2 / Story 2.3)
│       └── calls/[call_id]/page.tsx → Call detail placeholder (EPIC-3 / Story 3.2)
└── src/
    ├── api/client.ts              → proxyFetch, projectsAPI, callsAPI (EPIC-2/3)
    ├── utils/logger.ts            → Frontend console logger (EPIC-1 / Story 1.2)
    └── components/
        ├── TopNav.tsx             → Blue top nav bar (EPIC-2 / Story 2.3)
        ├── Sidebar.tsx            → Project list + per-project nav (EPIC-2 / Story 2.3)
        ├── KanbanBoard.tsx        → 4-column kanban (EPIC-3 / Story 3.2)
        ├── CallCard.tsx           → Call card with stage badge (EPIC-3 / Story 3.2)
        └── NewCallModal.tsx       → Create call form (EPIC-3 / Story 3.2)

transcription/
├── main.py                        → FastAPI local server: /health, /transcribe (EPIC-4 / Story 4.1)
├── transcribe.py                  → get_whisper(), get_pipeline(), transcribe_audio() (EPIC-4 / Story 4.1)
├── logger.py                      → Transcription logger factory (EPIC-4 / Story 4.1)
├── requirements.txt               → Transcription deps (fastapi, whisper, pyannote, torch)
└── tests/
    ├── test_transcribe.py         → 4 tests: unit + 3 API (EPIC-4 / Story 4.1)
    └── test_health.py             → 2 tests: health + rejection (EPIC-4 / Story 4.1)

run_transcription.sh               → Starts local transcription server on :8001 (EPIC-4 / Story 4.1)
```

---

## Key Modules

### `backend/routers/calls.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:**
- `GET /api/projects/{project_id}/calls` → list calls
- `POST /api/projects/{project_id}/calls` → create call (409 if active call exists)
- `GET /api/calls/{call_id}` → single call
- `PATCH /api/calls/{call_id}/stage` → advance stage (422 on skip; order: transcript→artifacts→topics→done)

**Stage order constant:** `STAGE_ORDER = ["transcript", "artifacts", "topics", "done"]`

---

### `backend/routers/projects.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:** `GET /api/projects`, `POST /api/projects`, `DELETE /api/projects/{id}`

---

### `transcription/transcribe.py`
**Exports:** `get_whisper()`, `get_pipeline()`, `transcribe_audio(audio_path, filename) → str`

**Model loading:** Lazy singletons via `_whisper_model` and `_diarization_pipeline` globals. `get_whisper()` loads `openai-whisper medium`. `get_pipeline()` loads `pyannote/speaker-diarization-3.1` — requires `HF_TOKEN` env var (raises `RuntimeError` if unset).

**Output format:** `[MM:SS] SPEAKER_X: text` per line. Speaker assigned by max-overlap between Whisper segment and pyannote diarization turns.

---

### `transcription/main.py`
**Local server on `localhost:8001`** — never deployed to Railway.
- `GET /health` → `{"status":"ok","models":"loaded"}`
- `POST /transcribe` → multipart `audio` field, .mp3 only, returns `{"transcript": str, "filename": str}`
- Lifespan preloads both models at startup
- CORS `allow_origins=["*"]`

---

## Dependency Map

| Module | Depends On | Used By |
|---|---|---|
| `backend/database.py` | `SUPABASE_URL`, `SUPABASE_KEY` env | all backend routers |
| `backend/logger.py` | — | all backend routers |
| `backend/routers/calls.py` | `database.py`, `logger.py` | `backend/main.py` |
| `backend/routers/projects.py` | `database.py`, `logger.py` | `backend/main.py` |
| `transcription/transcribe.py` | `transcription/logger.py`, `HF_TOKEN` env | `transcription/main.py` |
| `transcription/main.py` | `transcription/transcribe.py`, `transcription/logger.py` | `run_transcription.sh` |
| `frontend/src/api/client.ts` | Next.js proxy routes | all frontend components |

---

## Known Technical Debt

| # | Location | Description | Impact |
|---|---|---|---|
| TD-01 | `transcription/tests/` | `sys.path.insert` in test files instead of `conftest.py` | Tests fragile if directory layout changes |
| TD-02 | `transcription/tests/` | `test_health.py` duplicates coverage already in `test_transcribe.py` | Redundant maintenance |
