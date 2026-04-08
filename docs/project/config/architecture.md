# Architecture — Call Tracker
> **Status:** `[ ] Draft` → `[ ] Reviewed` → `[ ] Locked`
> ⚠️ Once LOCKED, changes require a new ADR entry in `workflow/ADR.md`.

---

## 1. Tech Stack

### Core

| Layer | Choice | Version | Reason |
|---|---|---|---|
| Language (backend) | Python | 3.11+ | FastAPI ecosystem, Whisper/pyannote compatibility |
| Language (frontend) | TypeScript | 5.x | Type safety across Next.js app |
| Framework (backend) | FastAPI | 0.111+ | Async support, SSE, Pydantic validation |
| Framework (frontend) | Next.js | 14.x (App Router) | Vercel-native, React 18 |
| Testing (backend) | pytest | 8.x | Standard Python testing |
| Testing (frontend) | Jest + Testing Library | 29.x | Matches existing template setup |
| Linter (backend) | ruff | latest | Fast, replaces flake8 + isort |
| Linter (frontend) | eslint | 8.x | Next.js default |
| Formatter (backend) | black | latest | Consistent Python formatting |
| Formatter (frontend) | prettier | 3.x | Consistent TypeScript formatting |

### Data & Storage

| Layer | Choice | Reason |
|---|---|---|
| Database | PostgreSQL (via Supabase) | Locked in PRD |
| BaaS | Supabase | Locked in PRD |
| ORM / Query | Supabase Python client (backend) + Supabase JS client (frontend, reads only) | No ORM overhead needed for this scope |
| Vector DB | none | Not needed |
| Caching | none | Solo-use, no caching required |
| File Storage | none | NG7 — transcripts stored as text in DB |

### Auth & Services

| Layer | Choice | Reason |
|---|---|---|
| Auth | none | Solo-use tool — no authentication required |
| Email | none | Out of scope v1 |
| Payments | none | Out of scope |
| AI / LLM | Anthropic Claude API (`claude-sonnet-4-6`) | Locked in PRD — artifacts + topic extraction |

### Infrastructure

| Layer | Choice | Reason |
|---|---|---|
| Hosting (frontend) | Vercel | Locked in PRD |
| Hosting (backend) | Railway | Locked in PRD |
| Local server | FastAPI on localhost | Transcription only — Whisper + pyannote, never on Railway |
| Containerization | none | Railway handles deployment without Docker |
| CI/CD | none | Manual deploy via git push to main |
| Monitoring | none | Solo-use, v1 — logs only |

### Approved External Packages

```
# Backend (Railway)
fastapi — API framework
uvicorn — ASGI server
pydantic — data validation
supabase — Supabase Python client
anthropic — Claude API SDK
python-multipart — file upload handling
httpx — async HTTP client

# Local Transcription Server (localhost only)
fastapi — API framework
uvicorn — ASGI server
openai-whisper — local speech-to-text (medium model)
pyannote.audio — speaker diarization
torch — required by Whisper + pyannote
watchdog — (optional) filesystem watcher if needed
ffmpeg — system install, audio processing

# Frontend (Vercel)
next — Next.js framework
react / react-dom — UI
typescript — type safety
tailwindcss — styling
@supabase/supabase-js — Supabase JS client (read-only queries)
```

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────┐
│              BROWSER (Next.js — Vercel)                  │
│  Project list · Kanban board · Call detail               │
│  Artifact editor · Topic dashboard                       │
│  Status badge: Local transcription Online/Offline        │
└───────────────────┬────────────────────┬────────────────┘
                    │ REST + SSE          │ REST (localhost)
                    ↓                    ↓
┌──────────────────────────┐  ┌─────────────────────────────┐
│  BACKEND API (Railway)   │  │  LOCAL TRANSCRIPTION SERVER │
│  FastAPI                 │  │  FastAPI on localhost:8000   │
│  - Projects CRUD         │  │  - POST /transcribe          │
│  - Calls CRUD + stage    │  │  - GET /health               │
│  - Artifact generation   │  │  Whisper (medium) +          │
│  - SSE streaming         │  │  pyannote speaker diarization│
│  - Topic extraction      │  │  Replicates transcribe_      │
│  - Claude API proxy      │  │  watcher.py 100%             │
└──────────────┬───────────┘  └─────────────────────────────┘
               │
               ↓
┌──────────────────────────┐     ┌──────────────────────┐
│  SUPABASE (PostgreSQL)   │     │  CLAUDE API          │
│  projects · calls        │     │  claude-sonnet-4-6   │
│  artifact_types          │     │  Artifact generation │
│  artifacts · topics      │     │  Topic extraction    │
│  topic_updates           │     └──────────────────────┘
└──────────────────────────┘
```

**Data Flow:**
1. User opens app (Next.js on Vercel) — frontend reads projects/calls directly from Supabase JS client
2. State-changing operations (generate artifacts, extract topics, advance stage) go through FastAPI on Railway
3. Artifact generation: FastAPI calls Claude API in parallel, streams status back via SSE
4. Topic extraction: FastAPI calls Claude API with transcript + artifact context
5. MP3 upload: browser calls local FastAPI (`localhost:8000/transcribe`) — transcript returned, stored via Railway backend
6. Local server health: browser pings `localhost:8000/health` every 30s — status badge updates

---

## 3. Component Breakdown

### Component 1: Frontend (Next.js — Vercel)
- **Responsibility:** All UI — project list, kanban board, call detail, artifact editor, topic dashboard, local server status badge
- **Input:** User interactions, Supabase JS reads, SSE stream from Railway, JSON from Railway
- **Output:** HTTP requests to Railway FastAPI, REST call to localhost for transcription
- **File location:** `frontend/`
  - `frontend/app/` — Next.js App Router pages
  - `frontend/app/page.tsx` — project list
  - `frontend/app/projects/[id]/page.tsx` — kanban + topic dashboard tabs
  - `frontend/app/projects/[id]/calls/[callId]/page.tsx` — call detail (stage-based view)
  - `frontend/src/components/kanban/` — KanbanBoard, CallCard, KanbanColumn
  - `frontend/src/components/artifacts/` — ArtifactSelector, ArtifactCard, ArtifactEditor
  - `frontend/src/components/topics/` — TopicList, TopicCard, TopicDashboard
  - `frontend/src/components/ui/` — shared UI components, TranscriptionStatusBadge
  - `frontend/src/api/` — API client (Railway + localhost)
  - `frontend/src/types/` — TypeScript type definitions
- **Key dependencies:** Next.js, React, TailwindCSS, @supabase/supabase-js, anthropic (none — Claude via Railway only)

### Component 2: Backend API (FastAPI — Railway)
- **Responsibility:** All business logic — artifact generation, topic extraction, Claude API calls, stage advancement, sequential call enforcement
- **Input:** HTTP requests from frontend
- **Output:** JSON responses, SSE streams
- **File location:** `backend/`
  - `backend/api/main.py` — FastAPI app, CORS, lifespan
  - `backend/api/routes/projects.py` — project CRUD
  - `backend/api/routes/calls.py` — call CRUD, stage advancement
  - `backend/api/routes/artifacts.py` — artifact generation (SSE), update, mark done
  - `backend/api/routes/artifact_types.py` — artifact type CRUD
  - `backend/api/routes/topics.py` — topic extraction, CRUD
  - `backend/api/services/claude_service.py` — Claude API wrapper (artifacts + topics)
  - `backend/api/models.py` — Pydantic models
  - `backend/database/connection.py` — Supabase client
  - `backend/database/schema.sql` — full DB schema
- **Key dependencies:** fastapi, uvicorn, anthropic, supabase, pydantic

### Component 3: Local Transcription Server (FastAPI — localhost)
- **Responsibility:** MP3 → transcript text. Replicates `transcribe_watcher.py` 100%. Never deployed to Railway.
- **Input:** MP3 file (multipart upload from browser)
- **Output:** Transcript text (timestamped, speaker-labeled)
- **File location:** `transcription/`
  - `transcription/server.py` — FastAPI app with /transcribe + /health endpoints
  - `transcription/transcribe.py` — Whisper + pyannote pipeline (ported from `transcribe_watcher.py`)
  - `transcription/requirements.txt` — heavy ML deps (torch, whisper, pyannote)
  - `transcription/run_transcription.sh` — one-command startup script
  - `transcription/setup.sh` — first-run: installs deps, downloads models, prompts HuggingFace token
- **Key dependencies:** fastapi, openai-whisper, pyannote.audio, torch, ffmpeg (system)

### Component 4: Database (Supabase PostgreSQL)
- **Responsibility:** All persistent data
- **Input:** Queries from Railway FastAPI (writes + reads) and Supabase JS client (reads only)
- **Output:** Query results
- **File location:** `backend/database/schema.sql`
- **Note:** No RLS required (solo-use), no Supabase Storage

---

## 4. Data Model

### projects
```
id:           uuid PRIMARY KEY DEFAULT gen_random_uuid()
name:         text NOT NULL
description:  text
created_at:   timestamptz DEFAULT now()
```

### calls
```
id:             uuid PRIMARY KEY DEFAULT gen_random_uuid()
project_id:     uuid REFERENCES projects(id) ON DELETE CASCADE
title:          text NOT NULL  -- user-defined, typically the call date
mp3_filename:   text           -- local reference only, never uploaded
transcript_text: text          -- stored after upload or transcription
kanban_stage:   text NOT NULL DEFAULT 'transcript'
                -- enum: transcript | artifacts | topics | done
created_at:     timestamptz DEFAULT now()
updated_at:     timestamptz DEFAULT now()
```

### artifact_types
```
id:           uuid PRIMARY KEY DEFAULT gen_random_uuid()
project_id:   uuid REFERENCES projects(id) ON DELETE CASCADE  -- null = global default
name:         text NOT NULL
prompt:       text NOT NULL
is_default:   boolean DEFAULT false  -- true for the 6 seeded defaults
created_at:   timestamptz DEFAULT now()
updated_at:   timestamptz DEFAULT now()
```

### artifacts
```
id:               uuid PRIMARY KEY DEFAULT gen_random_uuid()
call_id:          uuid REFERENCES calls(id) ON DELETE CASCADE
artifact_type_id: uuid REFERENCES artifact_types(id)
prompt_used:      text NOT NULL  -- snapshot at generation time, immutable
content:          text           -- generated or manually entered
mode:             text NOT NULL  -- enum: claude | manual
status:           text NOT NULL DEFAULT 'pending'
                  -- enum: pending | generating | done | error
error_message:    text           -- populated if status = error
created_at:       timestamptz DEFAULT now()
updated_at:       timestamptz DEFAULT now()
```

### topics
```
id:           uuid PRIMARY KEY DEFAULT gen_random_uuid()
project_id:   uuid REFERENCES projects(id) ON DELETE CASCADE
title:        text NOT NULL
status:       text NOT NULL DEFAULT 'active'
              -- enum: active | decision_made | on_hold | closed
first_call_id: uuid REFERENCES calls(id)  -- call where topic was first raised
created_at:   timestamptz DEFAULT now()
updated_at:   timestamptz DEFAULT now()
```

### topic_updates
```
id:             uuid PRIMARY KEY DEFAULT gen_random_uuid()
topic_id:       uuid REFERENCES topics(id) ON DELETE CASCADE
call_id:        uuid REFERENCES calls(id) ON DELETE CASCADE
summary:        text           -- what happened with this topic in this call
follow_up_items: text[]        -- open follow-up items after this call
created_at:     timestamptz DEFAULT now()
```

**Relationships:**
- project has many calls (sequential — one active at a time)
- project has many artifact_types (null project_id = global defaults)
- project has many topics
- call has many artifacts
- topic has many topic_updates (one per call where it appeared)

---

## 5. Folder Structure

```
call-tracker/
├── CLAUDE.md
├── README.md
│
├── backend/                          # FastAPI — deployed to Railway
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                   # App init, CORS, lifespan, seed defaults
│   │   ├── models.py                 # Pydantic request/response models
│   │   └── routes/
│   │       ├── projects.py
│   │       ├── calls.py
│   │       ├── artifacts.py          # Includes SSE generation endpoint
│   │       ├── artifact_types.py
│   │       └── topics.py
│   ├── services/
│   │   └── claude_service.py         # Claude API wrapper (artifacts + topics)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py             # Supabase client singleton
│   │   └── schema.sql                # Full DB schema
│   ├── tests/
│   │   ├── test_projects.py
│   │   ├── test_calls.py
│   │   ├── test_artifacts.py
│   │   └── test_topics.py
│   └── requirements.txt
│
├── transcription/                    # Local only — never deployed
│   ├── server.py                     # FastAPI: /health + /transcribe
│   ├── transcribe.py                 # Whisper + pyannote pipeline
│   ├── requirements.txt              # ML deps
│   ├── setup.sh                      # First-run model download
│   └── run_transcription.sh          # One-command startup
│
├── frontend/                         # Next.js — deployed to Vercel
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                  # Project list
│   │   ├── projects/
│   │   │   └── [id]/
│   │   │       ├── page.tsx          # Kanban + Topic Dashboard tabs
│   │   │       └── calls/
│   │   │           └── [callId]/
│   │   │               └── page.tsx  # Call detail (stage-based view)
│   │   └── globals.css
│   ├── src/
│   │   ├── components/
│   │   │   ├── kanban/               # KanbanBoard, KanbanColumn, CallCard
│   │   │   ├── artifacts/            # ArtifactSelector, ArtifactCard, ArtifactEditor
│   │   │   ├── topics/               # TopicDashboard, TopicCard, TopicList
│   │   │   └── ui/                   # TranscriptionStatusBadge, shared components
│   │   ├── api/
│   │   │   ├── backend.ts            # Railway FastAPI client
│   │   │   └── local.ts              # Localhost transcription client
│   │   └── types/
│   │       └── index.ts
│   ├── __tests__/
│   ├── package.json
│   ├── next.config.ts
│   └── tsconfig.json
│
├── docs/
│   └── project/
│       ├── requirements/             # Read-only templates
│       └── config/                   # Generated outputs
│
├── workflow/
│   ├── ADR.md
│   └── ERRORS.md
│
├── scripts/
│   ├── git_ops.py
│   └── setup.sh
│
└── logs/                             # gitignored
    ├── backend_YYYY-MM-DD.log
    ├── api_YYYY-MM-DD.log
    └── frontend_YYYY-MM-DD.log
```

---

## 6. Environment Variables

### Railway (backend)
| Variable | Description | Example |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | `https://xyz.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service role key (bypasses RLS) | `eyJ...` |
| `ANTHROPIC_API_KEY` | Claude API key | `sk-ant-...` |
| `FRONTEND_URL` | Vercel frontend URL (CORS) | `https://call-tracker.vercel.app,https://call-tracker-*.vercel.app` |
| `PORT` | Set automatically by Railway — do NOT set manually | — |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Vercel (frontend)
| Variable | Description | Example |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | `https://xyz.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key (safe for frontend reads) | `eyJ...` |
| `NEXT_PUBLIC_BACKEND_URL` | Railway FastAPI URL | `https://call-tracker-api.up.railway.app` |
| `NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL` | Local server URL | `http://localhost:8000` |

### Local Transcription (.env)
| Variable | Description | Example |
|---|---|---|
| `HUGGINGFACE_TOKEN` | Required for pyannote model download (one-time) | `hf_...` |
| `TRANSCRIPTION_PORT` | Local server port | `8000` |

---

## 7. API Design

### Projects
| Method | Endpoint | Body | Response |
|---|---|---|---|
| GET | `/api/projects` | — | `[{id, name, description, call_count, created_at}]` |
| POST | `/api/projects` | `{name, description}` | `{id, name, ...}` |
| GET | `/api/projects/{id}` | — | `{id, name, calls[], topics[]}` |
| DELETE | `/api/projects/{id}` | — | `204` |

### Calls
| Method | Endpoint | Body | Response |
|---|---|---|---|
| GET | `/api/projects/{id}/calls` | — | `[{id, title, kanban_stage, ...}]` |
| POST | `/api/projects/{id}/calls` | `{title, transcript_text, mp3_filename?}` | `{id, ...}` |
| GET | `/api/calls/{id}` | — | `{id, title, stage, transcript_text, artifacts[], ...}` |
| PATCH | `/api/calls/{id}/stage` | `{stage}` | `{id, kanban_stage}` |

### Artifact Types
| Method | Endpoint | Body | Response |
|---|---|---|---|
| GET | `/api/artifact-types` | — | `[{id, name, prompt, is_default, project_id}]` |
| POST | `/api/artifact-types` | `{name, prompt, project_id?}` | `{id, ...}` |
| PATCH | `/api/artifact-types/{id}` | `{name?, prompt?}` | `{id, ...}` |
| DELETE | `/api/artifact-types/{id}` | — | `204` |

### Artifacts
| Method | Endpoint | Body | Response |
|---|---|---|---|
| POST | `/api/calls/{id}/artifacts/generate` | `{artifact_configs: [{type_id, mode}]}` | `{artifact_ids[]}` then SSE |
| GET | `/api/calls/{id}/artifacts/stream` | — | SSE: `{artifact_id, status, content?}` |
| PATCH | `/api/artifacts/{id}` | `{content}` | `{id, content}` |
| PATCH | `/api/artifacts/{id}/done` | — | `{id, status: done}` |

### Topics
| Method | Endpoint | Body | Response |
|---|---|---|---|
| POST | `/api/calls/{id}/topics/extract` | — | `{topics[]}` (Claude extraction) |
| GET | `/api/projects/{id}/topics` | — | `[{id, title, status, updates[], first_call}]` |
| POST | `/api/projects/{id}/topics` | `{title, status?}` | `{id, ...}` |
| PATCH | `/api/topics/{id}` | `{title?, status?, follow_up_items?}` | `{id, ...}` |
| DELETE | `/api/topics/{id}` | — | `204` |
| POST | `/api/calls/{id}/topics/validate` | `{topic_updates[]}` | `204` — advances call to Done |

### Local Transcription (localhost:8000)
| Method | Endpoint | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{status: ok}` |
| POST | `/transcribe` | `multipart: {file: mp3}` | `{transcript_text, duration, speakers}` |

---

## 8. Key Technical Decisions

| Decision | Options Considered | Choice | Rationale |
|---|---|---|---|
| Real-time artifact progress | Polling / WebSockets / SSE | SSE | One-way server→client, native FastAPI support, simpler than WebSockets |
| Transcription location | Railway / local FastAPI | Local FastAPI | Whisper + pyannote too heavy for Railway; MP3 never leaves user's machine |
| Frontend DB access | All via Railway / direct Supabase reads | Hybrid — reads direct, writes via Railway | Reduces Railway load for reads; keeps all mutations in one place |
| Sequential call enforcement | UI only / API enforcement | Both | UI disables "New Call" button; API rejects if active call exists (double enforcement) |
| Artifact prompt snapshot | Live lookup / snapshot at generation | Snapshot stored on artifact | Editing prompts later must not alter historical artifacts |
| No auth / RLS | Supabase RLS / no auth | No auth, no RLS | Solo-use tool; service key in Railway only |
| Topic context on Call 2+ | Re-extract fresh / pass previous topics as context | Pass previous validated topics as context | Ensures continuity and avoids re-discovering resolved topics |

---

## 9. Integration Seams — Verify Before Coding

| Dependency | Format contract | Known edge cases | How to validate before coding |
|---|---|---|---|
| Claude API (anthropic SDK) | Messages API — `model`, `max_tokens`, `messages[]` required. Response in `content[0].text`. | Rate limits (429) on parallel calls; max_tokens must be set explicitly | Test single artifact call first; verify response shape; test 5 parallel calls and check for 429s |
| Supabase Python client | `supabase.table().insert/select/update/delete()` — returns `data` + `error`. Always check `error` before using `data`. | Service key bypasses RLS entirely — never expose to frontend | Verify connection with a simple `select` on `projects` table before building routes |
| Supabase JS client (frontend) | Anon key — public reads only. No RLS but anon key is restricted by table policies if set. | Anon key is visible in browser — only use for non-sensitive reads | Confirm anon key can read `projects` and `calls` tables without error |
| Local transcription (localhost→Vercel) | Browser calls `http://localhost:8000` from Vercel-hosted app. CORS must allow `https://*.vercel.app`. | Mixed content warning if Vercel is HTTPS and localhost is HTTP — browser may block. | Test in Chrome with CORS disabled first; then configure CORS on local FastAPI properly. Consider flagging "use .txt if transcription fails" |
| Railway env vars | All secrets single-line, no trailing whitespace or quotes. `PORT` auto-set by Railway. | Multi-line secrets (not applicable here) stripped. Trailing newline on copy-paste is common. | After adding each secret to Railway, verify in Raw Editor — no trailing chars |
| Vercel env vars | `NEXT_PUBLIC_` prefix required for client-side access. Build-time baked in. | Missing `NEXT_PUBLIC_` = `undefined` at runtime, no build error | After adding vars, trigger a redeploy; verify in browser console that `process.env.NEXT_PUBLIC_BACKEND_URL` is defined |
| CORS (FastAPI on Railway) | `CORSMiddleware` must be outermost middleware. Origins must include both production and preview Vercel URLs. | Error responses (500s) without CORS headers show as "Failed to fetch" in browser | Test an intentional 500 — browser must receive the error body, not a CORS failure |

---

## 10. Known Limitations & Technical Debt

- [ ] No pagination on topic dashboard — acceptable for solo-use (< 100 topics per project)
- [ ] No pagination on call list — acceptable for solo-use (< 50 calls per project)
- [ ] Local transcription server has no auth — acceptable since it's localhost only
- [ ] Mixed content (HTTPS Vercel → HTTP localhost) may require browser flag or workaround
- [ ] No retry UI on failed topic extraction — user must refresh and re-trigger
- [ ] Artifact SSE reconnection is basic — no persistent job queue

## Performance & Scalability Assumptions

- Expected load: 1 user, < 10 projects, < 50 calls per project, < 6 artifacts per call
- Architecture breaks at: concurrent multi-user access (no RLS, no auth)
- Scaling path if needed: add Supabase RLS + Clerk auth — no structural changes needed

---

## 11. Platform-Specific Gotchas

### Supabase
- No RLS needed (solo-use) — but service key must stay in Railway env only, never frontend
- No Storage buckets needed — transcripts stored as text, MP3 never uploaded
- Migrations are append-only — never edit an applied migration, always create a new file
- Seed the 6 default artifact types in an initial migration or on app startup (`is_default = true`)

### Railway
- `PORT` is auto-set by Railway — never set it manually in env vars
- Always verify secrets in Raw Editor after adding — no trailing spaces, quotes, or newlines
- Pin all Python dependencies explicitly in `requirements.txt` — no unpinned transitive deps
- CORS must be outermost FastAPI middleware layer (after all `@app.middleware` decorators)

### Vercel
- `NEXT_PUBLIC_BACKEND_URL` and `NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL` must have `NEXT_PUBLIC_` prefix
- Support comma-separated CORS origins in Railway `FRONTEND_URL` from day one — preview deployments use different URLs than production
- Trigger a redeploy after adding env vars — build-time vars are baked in at deploy time

### Local Transcription (localhost)
- Browser calling `http://localhost:8000` from `https://vercel.app` is a mixed-content request — Chrome blocks it by default. Solutions: (1) run local server on HTTPS with a self-signed cert, or (2) document that users must allow mixed content for localhost in Chrome settings
- Local FastAPI must set `allow_origins=["*"]` or include the Vercel domain explicitly for CORS
- First run requires `setup.sh` to download Whisper medium model (~1.5GB) and pyannote models
