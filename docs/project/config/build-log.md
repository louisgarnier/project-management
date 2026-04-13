# Build Log — Call Tracker

## Current Stage
**EPIC-6 — Topics Stage — COMPLETE**
- Status: Stories 6.1 + 6.2 done
- Blocked by: DB migration `002_topics_schema.sql` must be run in Supabase dashboard before end-to-end testing
- Next: EPIC-7 (not yet defined)

---

### 2026-04-13 — EPIC-6: Stories 6.1 + 6.2 — Topics API + Topics UI

**Story 6.1: Topics API (backend)**
- `backend/database/migrations/002_topics_schema.sql` — alters topics table: drops old `status` column, adds `calls_open INT`, `archived BOOL`; alters topic_updates: adds `decisions JSONB`, `status TEXT`, `owner TEXT`, `sentiment TEXT` — **must be run manually in Supabase dashboard**
- `backend/services/topics_service.py` — `TopicIn`, `TopicUpdate`, `TopicOut`, `BriefItem`, `BriefOut` Pydantic models; `extract_topics(call_id)` — regular fn returning coroutine (allows MagicMock in tests); Call 1 flat extraction, Call 2+ three-bucket (followed_up/not_discussed/new_topics); `save_topics(call_id, topics)` — upserts topic_updates, increments/resets calls_open; `validate_call(call_id)` — uses `_get_previous_topics()` to check latest status, raises ValueError with unacknowledged topic IDs; `generate_brief(call_id)` — priority/decisions/watch_list; `list_project_topics(project_id)`
- `backend/routers/topics.py` — 5 endpoints: POST /extract, POST /topics, POST /validate (422 on unacknowledged), GET /brief, GET /projects/{id}/topics
- `backend/main.py` — topics router registered
- `backend/tests/test_topics.py` — 9 tests (models + router); 86 total backend tests passing

**Story 6.2: Topics UI (frontend)**
- `frontend/src/types/index.ts` — replaced stale Topic types with: `TopicStatus`, `TopicOwner`, `TopicSentiment`, `TopicDisposition`, `TopicData`, `ExtractionResult`, `BriefItem`, `CallBrief`, `TopicSavePayload`
- `frontend/src/api/client.ts` — added `topicsAPI` (extract, save, validate, brief, listForProject)
- `frontend/src/components/PreCallBrief.tsx` — collapsible; lazy-loads `GET /brief` only on first open (NFR-08); shows priority topics / decisions to confirm / watch list; staleness badges; empty state
- `frontend/src/components/TopicEditor.tsx` — inline editable topic row; all 9 fields; decisions append-only; staleness badge when calls_open ≥ 2; disposition buttons (Keep as-is / Archive) for not_discussed bucket
- `frontend/src/components/AddTopicForm.tsx` — collapsed "+ Add topic" button; inline form with name/summary/status/owner/sentiment
- `frontend/src/components/TopicsStage.tsx` — state machine (choice/extracting/reviewing/manual/validating); three-bucket view for Call 2+, flat list for Call 1; ActionBar with disabled Validate until dispositions set; error states for extract and validate
- `frontend/src/components/TopicsDashboard.tsx` — table view; filter by status (All/Open/In Progress/Resolved); "Stale first" toggle; resolved rows at opacity 0.6; staleness badge when calls_open ≥ 2
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — TopicsStage wired for topics stage; green "Call complete" banner for done stage
- `frontend/app/projects/[id]/board/page.tsx` — Topics tab renders TopicsDashboard; board page reads `?tab=topics` query param to activate tab
- `frontend/app/projects/[id]/topics/page.tsx` — redirect shim to `/projects/{id}/board?tab=topics`

**Key decisions:**
- `_get_previous_topics()` helper reused across extract/validate/brief/list — single source of truth for "latest status per topic"
- `extract_topics` is a regular function returning a coroutine (not `async def`) to allow `MagicMock` in unit tests
- Three-bucket view gated on `call_number > 1` from extraction response — no separate DB query for call number
- `canValidate` gate: `topics.length > 0 && unacknowledgedCount === 0` — enforces disposition on all not_discussed topics
- Board tab query param uses `window.location.search` on mount (avoids Next.js `useSearchParams` + Suspense requirement)

---

## Session History

### 2026-04-12 — EPIC-6: Multi-LLM Support

**Feature: Multi-LLM Provider Selection**
- `backend/services/llm_service.py` — `generate_artifact(prompt_used, transcript, llm: str) → str`; dispatches to Groq (`llama-3.3-70b-versatile`), Claude (`claude-sonnet-4-6`), or OpenAI (`gpt-4o`); 3-retry exponential backoff on rate limit errors; API keys from `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`
- `backend/database/migrations/004_multi_llm.sql` — adds `default_llm TEXT` to `projects` table (default `'claude'`); adds `llm TEXT` to `artifact_types` table (nullable — null = inherit project default)
- `backend/routers/projects.py` — added `GET /api/projects/{project_id}` (single project) and `PATCH /api/projects/{project_id}` (update `default_llm`)
- `backend/routers/artifact_types.py` — `llm` field exposed on all read/write endpoints; nullable (null = inherit project default)
- `backend/routers/artifacts.py` — `POST /api/calls/{call_id}/artifacts` now accepts `llm` per selection; stream endpoint resolves effective LLM (artifact override → project default) and passes to `llm_service.generate_artifact`
- `backend/tests/test_llm_service.py` — 4 new tests: all three providers dispatch correctly, unknown provider raises ValueError
- `frontend/src/types/index.ts` — `default_llm` added to `Project`; `llm` (nullable) added to `ArtifactType`
- `frontend/src/api/client.ts` — `projectsAPI.get`, `projectsAPI.updateDefaultLlm`; `artifactTypesAPI` updated to include `llm` on create/update; `artifactsAPI.createSelections` accepts per-artifact `llm`
- `frontend/app/projects/[id]/artifacts/page.tsx` — per-artifact-type LLM dropdown; apply-to-all control
- `frontend/src/components/ArtifactTypeCard.tsx` — shows/edits `llm` field with inherit-project-default option
- `frontend/src/components/ArtifactSelector.tsx` — per-artifact LLM dropdown in generation flow; inherits project default when not set
- `frontend/src/components/ArtifactsStage.tsx` — passes resolved LLM per artifact to `createSelections`; apply-to-all LLM control in selection phase

**Files deleted:** `backend/services/claude_service.py` (replaced by `llm_service.py`)

**Tests:** 70 backend tests passing (4 new `test_llm_service` + 2 new artifacts + 2 new artifact_types + 4 new projects)

**Key decisions:**
- `llm` on `artifact_types` is nullable; null means "use project default" — not stored as a string
- Provider dispatch in `llm_service.py` uses a single `if/elif` — no dynamic import or registry
- `GROQ_API_KEY` uses `AsyncOpenAI` with `base_url=https://api.groq.com/openai/v1` (Groq is OpenAI-compatible)
- Apply-to-all sets all artifact type LLMs in state but does not persist unless user saves individually

---

### 2026-04-12 — EPIC-5: Story 5.4 — Artifacts Stage UI

**Story 5.4: Artifacts Stage UI**
- `backend/routers/artifacts.py` — added `GET /api/calls/{call_id}/artifacts` (list, 404 guard) and `PATCH /api/artifacts/{artifact_id}` (update content/status; 422 no-fields, 404 not-found); `ArtifactUpdate` Pydantic model
- `backend/tests/test_artifacts.py` — 5 new tests: list happy path, patch happy path, list 404, patch 422, patch 404 (58 total backend tests passing)
- `frontend/app/api/sse/[...path]/route.ts` — dedicated SSE proxy; passes `backendResponse.body` directly without buffering (unlike the JSON proxy); headers: `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- `frontend/src/api/client.ts` — added `artifactsAPI` (createSelections, list, update); added `callsAPI.advanceStage`; added `Artifact` to type imports
- `frontend/src/components/ArtifactSelector.tsx` — per-type row: Generate via Claude / Manual / Skip toggle buttons; exports `ArtifactMode` type
- `frontend/src/components/ArtifactCard.tsx` — status badge (pending/generating/done/error), spinner during generation, editable textarea, Mark Done button, inline `StatusBadge`
- `frontend/src/components/ArtifactsStage.tsx` — three-phase orchestrator: select → generating → reviewing; SSE consumption via ReadableStream + line buffer; `AbortController` cleanup on unmount; skips to reviewing if artifacts already exist
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — replaced "coming soon" placeholder with `ArtifactsStage` for artifacts stage; other past-transcript stages still show placeholder

**Key decisions:**
- SSE streams through `/api/sse/` not `/api/proxy/` (proxy buffers response.json())
- `streamArtifacts()` takes no arguments — uses closured `callId` from component scope
- `handleRetry` accepts `_artifactId` to match `ArtifactCard` prop type but re-streams all pending artifacts
- `ArtifactUpdate` filter uses `if v is not None` (not falsiness) — allows `content: ""` correctly

### 2026-04-12 — EPIC-5: Story 5.3 — Claude Service & SSE

**Story 5.3: Claude Service & SSE Endpoint**
- `backend/services/claude_service.py` — `generate_artifact(prompt_used, transcript) → str`; uses `AsyncAnthropic`, model `claude-sonnet-4-6`, 4 total attempts (3 retries) with exponential backoff (1s/2s/4s) on 429; logs start, token counts, errors
- `backend/routers/artifacts.py` — two endpoints:
  - `POST /api/calls/{call_id}/artifacts` — accepts `[{artifact_type_id, mode}]`; snapshots `prompt_used` from artifact type at creation; mode='manual' → status='done'; mode='claude' → status='pending'; 404 guard for call
  - `GET /api/calls/{call_id}/artifacts/stream` — SSE StreamingResponse; parallel generation via asyncio tasks + queue; emits `status`(generating) → `done`/`error` per artifact, `complete` at end; Cache-Control + X-Accel-Buffering headers
- `backend/tests/test_artifacts.py` — 5 tests; 53 total backend tests pass
- `backend/main.py` — artifacts router registered
- Plan: `docs/project/config/2026-04-12-story-5.3-claude-service-plan.md`

**Key decisions:**
- `prompt_used` is snapshotted at POST time — artifact type edits never affect generated history
- One artifact error does not block others (independent asyncio tasks, broad except)
- `Literal["claude", "manual"]` on mode field — invalid modes rejected with 422
- Supabase singleton client safe for concurrent coroutine use (each `.table()` creates independent query builder)

### 2026-04-12 — EPIC-5: Stories 5.1 + 5.2 — Artifacts Tab UI + API

**Story 5.1: Artifacts Tab UI**
- `frontend/app/projects/[id]/artifacts/page.tsx` — Artifacts page: load/error/empty states, delete/update handlers, modal trigger
- `frontend/src/components/ArtifactTypeCard.tsx` — expandable card: Default/Custom badge, expand/collapse prompt, inline edit (name + textarea), delete with confirm dialog, orange border on edit
- `frontend/src/components/AddArtifactTypeModal.tsx` — two-mode modal: Create new (name + prompt) + Import from another project (project dropdown → type checklist → multi-select confirm); error states for all API failures + retry
- `frontend/src/components/Sidebar.tsx` — added Artifacts (⚡) nav item between Board and Topics
- `frontend/src/types/index.ts` — added `project_id` to `ArtifactType`
- `frontend/src/api/client.ts` — `artifactTypesAPI`: list, create, update, delete, import

**Story 5.2: Artifact Types API**
- `backend/database/migrations/003_artifact_types_project_scoped.sql` — adds `project_id` FK (NOT NULL), clears old global seed rows
- `backend/routers/artifact_types.py` — GET, POST, PATCH, DELETE, POST /import; `seed_defaults()` exports 6 default types; 403 guard on default delete; import is intentionally cross-project
- `backend/tests/test_artifact_types.py` — 7 tests covering all endpoints and guards; 48 total backend tests pass
- `backend/routers/projects.py` — `seed_defaults(project["id"])` called after project creation
- `backend/main.py` — artifact_types router registered

**Key decisions:**
- artifact_types is project-scoped (project_id FK), not global
- Importing from another project creates independent copies (`is_default=False`)
- ArtifactTypeUpdate validates `min_length=1` to prevent empty-string writes
- Plan: `docs/project/config/2026-04-12-story-5.1-artifacts-tab-plan.md`

### 2026-04-10 — EPIC-4 closed: Story 4.6 + extras
**Story 4.6: Context File Attachments**
- Supabase Storage `call-files` bucket (manual setup)
- `backend/routers/files.py` — 4 endpoints: upload (multipart), list, delete, signed URL (60s TTL)
- `backend/tests/test_files.py` — 10 tests, all passing
- `frontend/src/types/index.ts` — `CallFile` interface
- `frontend/src/api/client.ts` — `proxyFetchForm`, `filesAPI` (upload, list, delete, downloadUrl), `callsAPI.resetTranscript`
- `frontend/src/components/ContextFiles.tsx` — upload + list + delete (editable) + download-only (readonly prop)
- `frontend/app/api/proxy/[...path]/route.ts` — multipart passthrough + 204 fix (`new NextResponse(null, {status:204})`)
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — ContextFiles wired in (readonly), reset transcript button for artifacts stage
- ADR-002 written for Supabase Storage adoption

**Extras built this session:**
- Delete project UI: `Sidebar.tsx` — "🗑 Delete project" button with confirm dialog, calls existing `DELETE /api/projects/{id}`
- Reset transcript: `DELETE /api/calls/{call_id}/transcript` (new backend endpoint) — rolls back artifacts → transcript, clears transcript + transcript_source via raw PATCH to bypass supabase-py None-filtering bug
- Transcript validate/review screen: `TranscriptStage.tsx` — after transcription, shows review screen with transcript preview + ContextFiles before advancing to Artifacts
- Time estimate calibration: formula `15 + 8s/MB` (was `20s/MB`); root cause was fixed 15s Metal JIT overhead per request
- Metal warmup: `transcription/transcribe.py` — `preload_model()` runs 0.5s silence dummy inference at startup to eliminate first-run latency spike

**Bug fixes:**
- 503 on delete project: `NextResponse.json(null, {status:204})` throws in Next.js → fixed to `new NextResponse(null, {status:204})`
- Transcript not cleared on reset: supabase-py silently drops `None` from `.update()` → fixed via `client.postgrest.session.patch()` with explicit `json.dumps()`

### 2026-04-10 — Story 4.8 (patch): Historical card UX fixes
- `CallCard.tsx` + `KanbanBoard.tsx` — historical badge shows column's stage label in green (was showing current stage in orange)
- `KanbanBoard.tsx` — historical card click appends `?view=${col.key}` to URL
- `TranscriptPanel.tsx` — added `defaultOpen` prop
- `calls/[call_id]/page.tsx` — `?view=transcript` renders transcript-only mode (no stage bar, panel expanded)

### 2026-04-10 — Story 4.8: Kanban History Trail + Persistent Transcript Panel
- `KanbanBoard.tsx` — column filter changed to show all calls that have reached or passed each stage; STAGE_INDEX map for O(1) lookups; projectId guard added
- `CallCard.tsx` — `isHistorical` prop: grey background + ✓ badge for historical cards; explicit `dimColor` in STAGE_CONFIG; `lineCount` memoized
- `TranscriptPanel.tsx` — new collapsible component: view/edit transcript via PATCH, download .txt; `savedText` state for accurate `isDirty`; robust download helper
- `calls/[call_id]/page.tsx` — TranscriptPanel wired in for all post-transcript stages

### 2026-04-10 — Story 4.7: Replace Transcription Engine with MLX Whisper
- Replaced openai-whisper + pyannote with mlx-whisper 0.4.3 (Apple Silicon Neural Engine)
- `transcription/transcribe.py` — rewritten: `preload_model()`, `transcribe_audio()` returns raw text (no timestamps/speaker labels)
- `transcription/main.py` — removed load_dotenv/Path, lifespan calls preload_model only
- `transcription/requirements.txt` — mlx-whisper==0.4.3, removed pyannote/openai-whisper/torchaudio
- `run_transcription.sh` — checks `import mlx_whisper`, rm -rf old venv before rebuild
- `transcription/.env` deleted, `.env.example` updated (no HF_TOKEN needed)
- 6/6 transcription tests pass, integration test confirmed raw text output

### 2026-04-10 — Story 4.5: Transcript Review, Edit & Download
- DB migration: `transcript_source TEXT` column added to `calls`
- `backend/routers/calls.py` — `POST /transcript` accepts `source_filename`, new `PATCH /transcript` endpoint (edit without stage change)
- 4 new tests, 31 total passing
- `frontend/src/types/index.ts` — `transcript_source: string | null` added to Call
- `frontend/src/api/client.ts` — `submitTranscript` accepts sourceFilename, added `updateTranscript`
- `frontend/src/components/TranscriptStage.tsx` — review step: upload → editable textarea → download/replace/save & continue
- `frontend/src/components/CallCard.tsx` — shows transcript line count + source filename

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
