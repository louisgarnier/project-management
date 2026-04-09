# Build Log — Call Tracker

## Current Stage
**EPIC-5 / Story 5.0 — Transcript Review & Redo**
- Status: not started
- Blocked by: nothing

---

## Session History

### 2026-04-09 — Story 4.4: Server Control UI
- `frontend/app/api/local/process.ts` — ChildProcess singleton (getServerProcess / setServerProcess)
- `frontend/app/api/local/start/route.ts` — POST: spawns run_transcription.sh, registers exit/error listeners
- `frontend/app/api/local/stop/route.ts` — POST: SIGTERM with try/catch guard
- `frontend/app/api/local/status/route.ts` — GET: health check + process-alive fallback → running / starting / offline
- `frontend/src/api/client.ts` — added `localServerAPI` (status, start, stop)
- `frontend/src/components/TranscriptionStatusBadge.tsx` — replaced with 4-state badge + Start/Stop buttons
- `frontend/src/components/TranscriptStage.tsx` — removed OfflineModal, inline error on offline MP3
- `frontend/src/components/OfflineModal.tsx` — deleted
- EPIC-4 closed — all 4 stories done

---

## Session History

### 2026-04-09 — Story 4.3: Transcript Stage UI
- `frontend/src/api/client.ts` — added `callsAPI.getCall`, `callsAPI.submitTranscript`, `transcriptionAPI` (health + transcribe, direct to localhost:8001)
- `frontend/src/components/TranscriptionStatusBadge.tsx` — polls health every 30s, green/orange badge
- `frontend/src/components/OfflineModal.tsx` — startup instructions, polls every 3s, auto-dismisses on server online
- `frontend/src/components/TranscriptStage.tsx` — MP3 and .txt file pickers, health check before MP3, uploading state + `beforeunload` guard, error state
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — fetches call, stage progress bar, routes to TranscriptStage for transcript stage
- EPIC-4 closed — all 3 stories done

### 2026-04-09 — Story 4.2: Transcript Stage Backend
- `POST /api/calls/{call_id}/transcript` added to `backend/routers/calls.py`
- `TranscriptSubmit` Pydantic model: `transcript: str = Field(min_length=1)`
- Guards: 404 if call not found, 409 if not at transcript stage, 422 if empty string
- Single DB update: sets `transcript` + advances `kanban_stage` to `artifacts`
- `backend/tests/test_transcript.py` — 5 tests (happy path, exact text, 404, 409, 422)
- 27/27 backend tests passing

### 2026-04-09 — Story 4.1: Local Transcription Server
- `transcription/transcribe.py` — `get_whisper()`, `get_pipeline()` (with HF_TOKEN guard), `transcribe_audio(path, filename) → str`
- `transcription/main.py` — refactored to import from transcribe.py; lifespan preloads both models at startup; `/health` returns `{"status":"ok","models":"loaded"}`; `/transcribe` mp3-only, 422 for other types
- `transcription/tests/test_transcribe.py` — 4 tests: unit test for transcribe_audio + 3 API tests (health, mp3-only guard, formatted transcript)
- `transcription/tests/test_health.py` — updated to use fixture-based mocking (lifespan now loads models)
- `run_transcription.sh` — already existed, unchanged
- 28/28 tests passing (6 transcription + 22 backend)



### 2026-04-09 — Story 3.2: Kanban Board UI
- Live BoardPage fetching calls from GET /api/projects/{id}/calls
- KanbanBoard: 4 columns (Get Transcript / Artifacts / Topics / Done) with CallCard per call
- CallCard: colored left border, stage badge, date, hover shadow, done opacity 0.65
- NewCallModal: title input, POST on submit, reloads board on success
- "+ New Call" disabled with tooltip when active call exists (hasActiveCall guard)
- Placeholder call detail page at /projects/[id]/calls/[call_id]
- Tabs: Kanban (live) + Topics (placeholder)
- TypeScript clean, ESLint clean, Prettier clean

### 2026-04-09 — Story 3.1: Calls API
- Implemented GET /api/projects/{id}/calls, POST /api/projects/{id}/calls, GET /api/calls/{id}, PATCH /api/calls/{id}/stage
- 409 sequential enforcement: only one active call per project
- Stage transitions: transcript → artifacts → topics → done (422 on skip)
- 9 new tests, 22 total passing
- ruff + black clean

### 2026-04-09 — EPIC-1 wrap-up + next@15 upgrade
**Completed:** EPIC-1 (Stories 1.1, 1.2, 1.3) verified and closed
**Fixes applied:**
- ruff auto-fixed 10 import-sort errors in backend/
- Recreated `backend/.env.example` (had been deleted)
- Upgraded `next@16.0.3` (CVE) → `next@15.x` (stable, 0 vulnerabilities)
- Upgraded `eslint@8` → `eslint@9` (flat config via `@eslint/eslintrc` FlatCompat)
- Created `frontend/eslint.config.mjs` replacing `.eslintrc.json`
- Fixed `frontend/src/utils/logger.ts` — ternary-as-statement → if/else
- Logged upgrade as ADR-001

**Verification (all passing):**
- 8/8 backend tests pass
- ruff: 0 errors, black: 0 changes
- ESLint (frontend): 0 errors, 0 warnings

**Next session starts at:** EPIC-2 / Story 2.1 — Projects API

### 2026-04-09 — EPIC-2 / Story 2.1 — Projects API
**Completed:** Projects CRUD API
**Built:**
- `backend/routers/projects.py` — GET /api/projects, POST /api/projects, DELETE /api/projects/{id}
- `backend/main.py` — router registered with `/api` prefix
- `backend/tests/test_projects.py` — 5 tests (TDD, all passing)

**Verification:**
- 13/13 backend tests pass
- 404 on delete non-existent project (not 500)
- db_logger on every Supabase operation

**Next session starts at:** EPIC-2 / Story 2.2 — Project List UI

### 2026-04-09 — EPIC-2 / Story 2.2 — Project List UI
**Completed:** Project list, create modal, project detail placeholder
**Built:**
- `frontend/app/page.tsx` — fetches projects, shows list + create button
- `frontend/src/components/ProjectList.tsx` — list with empty state
- `frontend/src/components/CreateProjectModal.tsx` — form (name + description)
- `frontend/app/projects/[id]/page.tsx` — placeholder page
- `frontend/src/api/client.ts` — added `projectsAPI` (list, create, delete)

**Verification:**
- ESLint: 0 errors
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement

### 2026-04-09 — EPIC-2 / Story 2.3 — App Shell & Project List UI (Redesign)
**Completed:** Jira-like app shell — top nav, sidebar, per-project nav, placeholder pages
**Built:**
- `frontend/src/components/TopNav.tsx` — blue top nav (static server component)
- `frontend/src/components/Sidebar.tsx` — client component, project list + per-project nav, create modal, hash-stable colours, error logging
- `frontend/src/components/CallCard.tsx` — placeholder card component for EPIC-3
- `frontend/app/layout.tsx` — root layout with shell (TopNav + Sidebar + main)
- `frontend/app/page.tsx` — "select a project" landing
- `frontend/app/projects/[id]/page.tsx` — redirects to /board
- `frontend/app/projects/[id]/board/page.tsx` — 4-column kanban placeholder
- `frontend/app/projects/[id]/topics/page.tsx` — placeholder
- `frontend/app/projects/[id]/history/page.tsx` — placeholder
- Deleted `frontend/src/components/ProjectList.tsx`

**Verification:**
- ESLint: 0 errors, 0 warnings
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement
