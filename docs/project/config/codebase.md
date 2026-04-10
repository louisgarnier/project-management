# Codebase Map — Call Tracker
> Updated after every story. Read this before touching any existing module.
> Last updated: EPIC-4 / Story 4.5

---

## Module Index

```
backend/
├── main.py                        → FastAPI entry point, router registration (EPIC-1 / Story 1.1)
├── database.py                    → Supabase client factory (EPIC-1 / Story 1.3)
├── logger.py                      → Backend logger (EPIC-1 / Story 1.2)
├── routers/
│   ├── projects.py                → GET/POST/DELETE /api/projects (EPIC-2 / Story 2.1)
│   └── calls.py                   → GET/POST /api/projects/{id}/calls, PATCH /api/calls/{id}/stage, POST /api/calls/{id}/transcript (EPIC-3/4)
└── tests/
    ├── test_projects.py           → 5 tests for projects API (EPIC-2 / Story 2.1)
    ├── test_calls.py              → 9 tests for calls API (EPIC-3 / Story 3.1)
    └── test_transcript.py         → 5 tests: happy path, exact text, 404, 409, 422 (EPIC-4 / Story 4.2)

frontend/
├── app/
│   ├── layout.tsx                 → Root layout: TopNav + Sidebar + main (EPIC-2 / Story 2.3)
│   ├── page.tsx                   → Landing: "select a project" (EPIC-2 / Story 2.3)
│   └── projects/[id]/
│       ├── page.tsx               → Redirects to /board (EPIC-2 / Story 2.3)
│       ├── board/page.tsx         → Kanban board (live calls) (EPIC-3 / Story 3.2)
│       ├── topics/page.tsx        → Placeholder (EPIC-2 / Story 2.3)
│       ├── history/page.tsx       → Placeholder (EPIC-2 / Story 2.3)
│       ├── calls/[call_id]/page.tsx → Call detail page: stage router, progress bar (EPIC-4 / Story 4.3)
│       └── api/local/
│           ├── process.ts             → ChildProcess singleton (EPIC-4 / Story 4.4)
│           ├── start/route.ts         → POST: spawn run_transcription.sh (EPIC-4 / Story 4.4)
│           ├── stop/route.ts          → POST: SIGTERM transcription process (EPIC-4 / Story 4.4)
│           └── status/route.ts        → GET: running / starting / offline (EPIC-4 / Story 4.4)
└── src/
    ├── api/client.ts              → proxyFetch, projectsAPI, callsAPI (getCall, submitTranscript), transcriptionAPI (EPIC-2/3/4)
    ├── utils/logger.ts            → Frontend console logger (EPIC-1 / Story 1.2)
    └── components/
        ├── TopNav.tsx             → Blue top nav bar (EPIC-2 / Story 2.3)
        ├── Sidebar.tsx            → Project list + per-project nav (EPIC-2 / Story 2.3)
        ├── KanbanBoard.tsx        → 4-column kanban (EPIC-3 / Story 3.2)
        ├── CallCard.tsx           → Call card with stage badge (EPIC-3 / Story 3.2)
        ├── NewCallModal.tsx       → Create call form (EPIC-3 / Story 3.2)
        ├── TranscriptionStatusBadge.tsx → 4-state badge (offline/starting/online/stopping) + Start/Stop buttons (EPIC-4 / Story 4.4)
        └── TranscriptStage.tsx    → MP3/TXT upload → review screen (edit, download, replace, save & continue) (EPIC-4 / Story 4.5)

transcription/
├── main.py                        → FastAPI local server: /health, /transcribe (EPIC-4 / Story 4.7)
├── transcribe.py                  → preload_model(), transcribe_audio() — mlx-whisper engine (EPIC-4 / Story 4.7)
├── logger.py                      → Transcription logger factory (EPIC-4 / Story 4.1)
├── requirements.txt               → Transcription deps (fastapi, mlx-whisper, torch)
└── tests/
    ├── test_transcribe.py         → 4 tests: unit + API (mlx-whisper mocks) (EPIC-4 / Story 4.7)
    └── test_health.py             → 2 tests: health + rejection (EPIC-4 / Story 4.7)

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
- `POST /api/calls/{call_id}/transcript` → store transcript + source_filename, advance to artifacts
- `PATCH /api/calls/{call_id}/transcript` → edit transcript without stage change (409 if still at transcript stage)

**Stage order constant:** `STAGE_ORDER = ["transcript", "artifacts", "topics", "done"]`

---

### `backend/routers/projects.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:** `GET /api/projects`, `POST /api/projects`, `DELETE /api/projects/{id}`

---

### `transcription/transcribe.py`
**Exports:** `preload_model()`, `transcribe_audio(audio_path, filename) → str`

**Model loading:** `preload_model()` warms up `mlx-community/whisper-large-v3-turbo` via `ModelHolder.get_model()` at server startup. Runs on Apple Silicon Neural Engine via `mlx-whisper 0.4.3`. No HF_TOKEN required.

**Output format:** Raw text string — no timestamps, no speaker labels. `result["text"].strip()` from mlx_whisper.

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
| `transcription/transcribe.py` | `transcription/logger.py`, `mlx-whisper`, `mlx.core` | `transcription/main.py` |
| `transcription/main.py` | `transcription/transcribe.py`, `transcription/logger.py` | `run_transcription.sh` |
| `frontend/src/api/client.ts` | Next.js proxy routes | all frontend components |

---

## Known Technical Debt

| # | Location | Description | Impact |
|---|---|---|---|
| TD-01 | `transcription/tests/` | `sys.path.insert` in test files instead of `conftest.py` | Tests fragile if directory layout changes |
| TD-02 | `transcription/tests/` | `test_health.py` duplicates coverage already in `test_transcribe.py` | Redundant maintenance |
