# Codebase Map — Call Tracker
> Updated after every story. Read this before touching any existing module.
> Last updated: EPIC-6 / Multi-LLM (2026-04-12)

---

## Module Index

```
backend/
├── main.py                        → FastAPI entry point, router registration (EPIC-1 / Story 1.1)
├── database.py                    → Supabase client factory (EPIC-1 / Story 1.3)
├── logger.py                      → Backend logger (EPIC-1 / Story 1.2)
├── routers/
│   ├── projects.py                → GET/POST/DELETE /api/projects, GET/PATCH /api/projects/{id}; seeds 6 default artifact types on POST; PATCH updates default_llm (EPIC-2 / Story 2.1, EPIC-5 / Story 5.2, EPIC-6)
│   ├── calls.py                   → GET/POST /api/projects/{id}/calls, PATCH /api/calls/{id}/stage, POST/PATCH/DELETE /api/calls/{id}/transcript (EPIC-3/4)
│   ├── files.py                   → POST/GET/DELETE /api/calls/{id}/files, GET signed URL (EPIC-4 / Story 4.6)
│   ├── artifact_types.py          → GET/POST/PATCH/DELETE /api/projects/{id}/artifact-types, POST /import; seed_defaults(); llm field (nullable, null=inherit project default) (EPIC-5 / Story 5.2, EPIC-6)
│   └── artifacts.py               → POST /api/calls/{id}/artifacts (create selections), GET /api/calls/{id}/artifacts (list), PATCH /api/artifacts/{id} (update), GET /stream SSE (parallel generation) (EPIC-5 / Stories 5.3 + 5.4)
└── tests/
    ├── test_projects.py           → 9 tests for projects API: CRUD + GET single + PATCH default_llm (EPIC-2 / Story 2.1, EPIC-6)
    ├── test_calls.py              → 9 tests for calls API (EPIC-3 / Story 3.1)
    ├── test_transcript.py         → 5 tests: happy path, exact text, 404, 409, 422 (EPIC-4 / Story 4.2)
    ├── test_files.py              → 10 tests: upload, list, delete, download, 404s, 422s (EPIC-4 / Story 4.6)
    ├── test_artifact_types.py     → 9 tests: list, create, update, delete (custom/default/404), import + 2 new EPIC-6 llm field tests (EPIC-5 / Story 5.2, EPIC-6)
    ├── test_artifacts.py          → 12 tests: POST create, prompt snapshot, SSE happy path, SSE error isolation, empty pending, list artifacts, list 404, patch content, patch 422, patch 404 + 2 new EPIC-6 (EPIC-5 / Stories 5.3 + 5.4, EPIC-6)
    └── test_llm_service.py        → 4 tests: claude dispatch, groq dispatch, openai dispatch, unknown provider ValueError (EPIC-6)

frontend/
├── app/
│   ├── layout.tsx                 → Root layout: TopNav + Sidebar + main (EPIC-2 / Story 2.3)
│   ├── page.tsx                   → Landing: "select a project" (EPIC-2 / Story 2.3)
│   └── projects/[id]/
│       ├── page.tsx               → Redirects to /board (EPIC-2 / Story 2.3)
│       ├── board/page.tsx         → Kanban board (live calls) (EPIC-3 / Story 3.2)
│       ├── topics/page.tsx        → Placeholder (EPIC-2 / Story 2.3)
│       ├── history/page.tsx       → Placeholder (EPIC-2 / Story 2.3)
│       ├── artifacts/page.tsx     → Artifacts tab: list all artifact types, delete/update, + Add modal (EPIC-5 / Story 5.1)
│       ├── calls/[call_id]/page.tsx → Call detail page: stage router, progress bar (EPIC-4 / Story 4.3)
│       ├── api/sse/[...path]/route.ts → GET: SSE proxy — streams backendResponse.body without buffering (EPIC-5 / Story 5.4)
│       └── api/local/
│           ├── process.ts             → ChildProcess singleton (EPIC-4 / Story 4.4)
│           ├── start/route.ts         → POST: spawn run_transcription.sh (EPIC-4 / Story 4.4)
│           ├── stop/route.ts          → POST: SIGTERM transcription process (EPIC-4 / Story 4.4)
│           └── status/route.ts        → GET: running / starting / offline (EPIC-4 / Story 4.4)
└── src/
    ├── api/client.ts              → proxyFetch, proxyFetchForm, projectsAPI, callsAPI (getCall, submitTranscript, updateTranscript, resetTranscript, advanceStage), transcriptionAPI, filesAPI, localServerAPI, artifactTypesAPI, artifactsAPI (createSelections, list, update) (EPIC-2/3/4/5)
    ├── utils/logger.ts            → Frontend console logger (EPIC-1 / Story 1.2)
    ├── utils/callColors.ts        → Shared 8-color pastel palette + callColor() helper for per-call index rendering (EPIC-10 / Story 10.9)
    ├── utils/provenance.ts        → Pure resolveProvenance(items, history, section) — exact-string match of items against topic's per-call history; powers pill rendering (EPIC-10 / Story 10.9)
    └── components/
        ├── TopNav.tsx             → Blue top nav bar (EPIC-2 / Story 2.3)
        ├── Sidebar.tsx            → Project list + per-project nav + delete project (EPIC-2 / Story 2.3 + EPIC-4 extra)
        ├── KanbanBoard.tsx        → history trail kanban: each column shows all calls that have reached or passed that stage; active vs historical card differentiation (EPIC-4 / Story 4.8)
        ├── CallCard.tsx           → Call card with stage badge (EPIC-3 / Story 3.2)
        ├── NewCallModal.tsx       → Create call form (EPIC-3 / Story 3.2)
        ├── TranscriptionStatusBadge.tsx → 4-state badge (offline/starting/online/stopping) + Start/Stop buttons (EPIC-4 / Story 4.4)
        ├── TranscriptStage.tsx    → MP3/TXT upload → review screen (edit, download, replace, ContextFiles, validate & send to Artifacts) (EPIC-4 / Story 4.5 + 4.6)
        ├── TranscriptPanel.tsx    → collapsible transcript viewer/editor (PATCH save, download .txt) — shown on call detail for post-transcript stages (EPIC-4 / Story 4.8)
        ├── ContextFiles.tsx       → context file list with upload/delete (editable) or download-only (readonly prop); 10MB guard, accepted types: .txt .pdf .docx .csv .md (EPIC-4 / Story 4.6)
        ├── ArtifactTypeCard.tsx   → expandable artifact type card: Default/Custom badge, expand prompt, inline edit (name + textarea, orange border), delete with confirm (EPIC-5 / Story 5.1)
        ├── AddArtifactTypeModal.tsx → two-mode modal: Create new (name + prompt) + Import from another project (project selector → checklist); error states + retry (EPIC-5 / Story 5.1)
        ├── ArtifactSelector.tsx   → per-type row: Generate via Claude / Manual / Skip toggle buttons; exports ArtifactMode type (EPIC-5 / Story 5.4)
        ├── ArtifactCard.tsx       → status badge, editable textarea, spinner during generation, Mark Done button, inline StatusBadge (EPIC-5 / Story 5.4)
        ├── ArtifactsStage.tsx     → three-phase orchestrator (select → generating → reviewing); SSE via ReadableStream + line buffer; AbortController cleanup; skips to reviewing if artifacts exist (EPIC-5 / Story 5.4)
        └── ProvenancePill.tsx     → compact pill showing origin call of a follow-up/decision item (EPIC-10 / Story 10.9)

backend/prompts/
├── call_topics.py                 → CALL_TOPICS_DEFAULT_PROMPT (ROLE/RUBRIC/ANCHORS/FEW-SHOT/PROCESS blocks) + OLD_DEFAULT_PROMPT_STRING snapshot (EPIC-11 / Story 11.1–11.2)
├── project_topics.py              → PROJECT_TOPICS_DEFAULT_PROMPT constant (EPIC-11 / Story 11.2)
├── merge_verification.py          → MERGE_VERIFICATION_DEFAULT_PROMPT constant (EPIC-11 / Story 11.2)
├── not_discussed_check.py         → NOT_DISCUSSED_DEFAULT_PROMPT constant (EPIC-11 / Story 11.2)
└── artifacts.py                   → DEFAULT_ARTIFACT_PROMPTS dict bundling all artifact-type default prompts (EPIC-11 / Story 11.2)

backend/scripts/
└── migrate_call_topics_prompt.py  → one-shot migration; replaces old-default call_topics prompts with new rubric-driven default; preserves customized rows; returns {migrated: N, preserved: M} (EPIC-11 / Story 11.2)

backend/services/
├── llm_service.py                 → generate_artifact(prompt_used, transcript, llm, *, model=None) + call_llm_raw(llm, *, model=None) → str; dispatches to Groq / Claude / OpenAI / DeepSeek / OpenRouter (5th provider via AsyncOpenAI + openrouter.ai/api/v1); model required for openrouter; 3-retry backoff (EPIC-6, EPIC-11 / Story 11.3)
├── topics_service.py              → topic extraction + aggregation + merge pipeline; uses topic_lineage for per-topic evidence blocks in merge prompts (EPIC-7/9/10)
└── topic_lineage.py               → walks merged_into_topic_id backwards to assemble ancestor-aware per-topic history. Exports get_topic_lineage, get_lineage_topic_updates, get_lineage_match_groups, build_lineage_evidence_block. Single source of truth for M:N merge history — consumed by merge prompts today and by the future evidence API (EPIC-10 / Story 10.1)

frontend/src/constants/
└── models.ts                      → MODEL_RECOMMENDATIONS per ArtifactCategory (curated model slugs for each category) + PROVIDER_LABELS mapping provider keys to display strings including OpenRouter ⭐ (EPIC-11 / Story 11.4)

transcription/
├── main.py                        → FastAPI local server: /health, /transcribe (EPIC-4 / Story 4.7)
├── transcribe.py                  → preload_model(), transcribe_audio() — mlx-whisper engine (EPIC-4 / Story 4.7)
├── logger.py                      → Transcription logger factory (EPIC-4 / Story 4.1)
├── requirements.txt               → Transcription deps (fastapi, mlx-whisper, torch)
└── tests/
    ├── test_transcribe.py         → 4 tests: unit + API (mlx-whisper mocks) (EPIC-4 / Story 4.7)
    └── test_health.py             → 2 tests: health + rejection (EPIC-4 / Story 4.7)

run_transcription.sh               → Starts local transcription server on :8001 (EPIC-4 / Story 4.1)

backend/templates/
├── next_steps.py                  → Template renderer: formats follow_up_items[] into ## topic / - **Owner:** action markdown (EPIC-12 / Story 12.1)
├── questions_list.py              → Template renderer: formats open_questions[] grouped by topic (EPIC-12 / Story 12.1)
├── agenda_skeleton.py             → Template renderer: filters resolved topics, sorts concern-first, renders agenda bullets (EPIC-12 / Story 12.1)
├── risk_register.py               → Template renderer: includes only sentiment=concern OR is_parked=true topics (EPIC-12 / Story 12.1)
├── decisions_digest.py            → Template renderer: flattens decisions[] across all topics grouped by topic (EPIC-12 / Story 12.1)
└── registry.py                    → Maps template_id keys to render functions (EPIC-12 / Story 12.1)

backend/library/
└── seed.py                        → SYSTEM_LIBRARY list[dict] with 8 canonical entries (3 seeded_by_default) + idempotent upsert_system_library(db) (EPIC-12 / Story 12.2)

backend/routers/
└── library.py                     → GET/POST/PATCH/DELETE /api/library + POST /api/library/reset-system; system entries 403 on DELETE; reset re-applies SYSTEM_LIBRARY (EPIC-12 / Story 12.2)

backend/services/
└── template_service.py            → dispatch_template(artifact_type, topics) → markdown str; routes by template_id via registry (EPIC-12 / Story 12.3)

frontend/app/library/
└── page.tsx                       → Top-level library management page: System / Yours sections, reset-system button (EPIC-12 / Story 12.5)

frontend/src/components/
├── LibraryEntryCard.tsx           → Inline edit/delete for a library entry; Delete hidden for system entries (EPIC-12 / Story 12.5)
└── PublishToLibraryDialog.tsx     → Modal: name + description fields, posts to /api/artifact-types/{id}/publish-to-library (EPIC-12 / Story 12.5)
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
- `DELETE /api/calls/{call_id}/transcript` → roll back artifacts → transcript, set transcript + transcript_source to NULL (bypasses supabase-py None-filtering bug via raw httpx session patch)

**Stage order constant:** `STAGE_ORDER = ["transcript", "artifacts", "topics", "done"]`

---

### `backend/routers/files.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:**
- `POST /api/calls/{call_id}/files` → multipart upload to Supabase Storage `call-files` bucket + DB record; 422 for wrong type/size; storage rollback if DB insert fails
- `GET /api/calls/{call_id}/files` → list `call_files` rows for call
- `DELETE /api/calls/{call_id}/files/{file_id}` → delete from storage + DB; 404 if not found
- `GET /api/calls/{call_id}/files/{file_id}/download` → return 60s signed URL via `create_signed_url()`

**Constants:** `ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE = 10 * 1024 * 1024`, `SIGNED_URL_TTL_SECONDS = 60`

**Security:** `os.path.basename(file.filename)` prevents path traversal in storage key.

---

### `backend/routers/projects.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:**
- `GET /api/projects` → list all projects
- `POST /api/projects` → create project (side effect: calls `seed_defaults(project_id)` to insert 6 default artifact types)
- `DELETE /api/projects/{id}` → delete project
- `GET /api/projects/{project_id}` → single project
- `PATCH /api/projects/{project_id}` → update `default_llm` (accepts `"claude"`, `"groq"`, `"openai"`)

---

### `backend/routers/artifacts.py`
**Exports:** `router` (APIRouter, prefix `/api`)
**Endpoints:**
- `POST /api/calls/{call_id}/artifacts` — accepts `{selections: [{artifact_type_id, mode: "claude"|"manual"}]}`; snapshots `prompt_used` from artifact type; mode='manual' → status='done'; mode='claude' → status='pending'; 404 if call not found
- `GET /api/calls/{call_id}/artifacts` — list all artifacts for call (ordered by created_at); 404 if call not found
- `PATCH /api/artifacts/{artifact_id}` — update content and/or status; 422 if no fields; 404 if not found
- `GET /api/calls/{call_id}/artifacts/stream` — SSE; fetches pending artifacts, runs all in parallel via asyncio tasks + queue; emits `status`→`done`/`error` per artifact, `complete` at end; headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`

---

### `backend/routers/artifact_types.py`
**Exports:** `router` (APIRouter, prefix `/api`), `seed_defaults(project_id: str)`
**Endpoints:**
- `GET /api/projects/{project_id}/artifact-types` → list all types for project (ordered by created_at)
- `POST /api/projects/{project_id}/artifact-types` → create custom type (is_default=False); accepts optional `llm` field
- `PATCH /api/projects/{project_id}/artifact-types/{type_id}` → update name, prompt, and/or llm; 404 if not found
- `DELETE /api/projects/{project_id}/artifact-types/{type_id}` → 403 if default; 404 if not found; 204 on success
- `POST /api/projects/{project_id}/artifact-types/import` → fetch source types by ID (cross-project), insert copies with new project_id and is_default=False

**`llm` field:** nullable TEXT on `artifact_types`; `null` means inherit the project's `default_llm`; explicit values: `"claude"`, `"groq"`, `"openai"`.

**`seed_defaults(project_id)`:** inserts 6 default types (Executive Summary, Next Steps & Action Items, Questions for Stakeholders, Email Summary 1-pager, Email Follow-up, Next Call Meeting Invite Topics).

---

### `backend/services/llm_service.py`
**Exports:** `generate_artifact(prompt_used, transcript, llm: str) → str`

**Providers:**
- `"claude"` → AsyncAnthropic, claude-sonnet-4-6, 3-retry exponential backoff on RateLimitError
- `"groq"` → AsyncOpenAI (base_url=https://api.groq.com/openai/v1), llama-3.3-70b-versatile
- `"openai"` → AsyncOpenAI, gpt-4o

**Config:** API keys from env — `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`

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
