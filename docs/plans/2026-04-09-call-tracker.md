# Call Tracker Implementation Plan — Vertical Slices

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Call Tracker slice by slice — each slice ends with something the user can open in a browser and test before the next slice begins. Frontend and backend are built together per feature.

**Architecture:** Next.js (Vercel/local) ↔ FastAPI (Railway/local) ↔ Supabase (PostgreSQL). Local FastAPI also handles MP3 transcription (Whisper + pyannote). SSE streams artifact generation progress.

**Tech Stack:** Python 3.11 / FastAPI / Supabase Python client / Anthropic SDK / Next.js 14 App Router / TypeScript / TailwindCSS

**How to run locally during development:**
- Backend: `cd backend && uvicorn api.main:app --reload --port 8001`
- Frontend: `cd frontend && npm run dev` → opens at `http://localhost:3000`
- Local transcription: `cd transcription && ./run_transcription.sh` → runs at `http://localhost:8000`

**Reference:**
- `docs/project/config/prd.md` — locked requirements
- `docs/project/config/architecture.md` — locked architecture
- `/Users/louisgarnier/Claude/PM/transcribe_watcher.py` — transcription logic to replicate 100%

---

## Slice 1: App Runs — Empty Project List

**What you see at the end:** Browser opens at `localhost:3000`, shows "Call Tracker" nav bar and an empty "Projects" page. Backend health check returns `{"status": "ok"}`.

---

### Task 1.1: Supabase schema + seed

**Files:**
- Create: `backend/database/schema.sql`
- Create: `backend/database/seed.sql`

- [ ] **Step 1: Write schema.sql**

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE calls (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title            TEXT NOT NULL,
  mp3_filename     TEXT,
  transcript_text  TEXT,
  kanban_stage     TEXT NOT NULL DEFAULT 'transcript'
                   CHECK (kanban_stage IN ('transcript','artifacts','topics','done')),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE artifact_types (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID REFERENCES projects(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  prompt       TEXT NOT NULL,
  is_default   BOOLEAN NOT NULL DEFAULT false,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE artifacts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id          UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  artifact_type_id UUID NOT NULL REFERENCES artifact_types(id),
  prompt_used      TEXT NOT NULL,
  content          TEXT,
  mode             TEXT NOT NULL CHECK (mode IN ('claude','manual')),
  status           TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','generating','done','error')),
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE topics (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title          TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','decision_made','on_hold','closed')),
  first_call_id  UUID REFERENCES calls(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE topic_updates (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id         UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  call_id          UUID REFERENCES calls(id) ON DELETE SET NULL,
  summary          TEXT,
  follow_up_items  TEXT[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Run schema.sql in Supabase SQL Editor**

Open Supabase dashboard → SQL Editor → paste and run.
Verify 6 tables appear in Table Editor.

- [ ] **Step 3: Write seed.sql**

```sql
INSERT INTO artifact_types (name, prompt, is_default, sort_order) VALUES
('Executive Summary',
 'You are analyzing a client call transcript. Write a structured executive summary covering: (1) Key points — decisions made, next steps, challenges, accountability gaps, goals. (2) Main topics in bullet points. (3) Any processes or flows discussed as a logical sequence. Be concise and factual.\n\nTranscript:\n{{transcript}}',
 true, 1),
('Next Steps & Action Items',
 'From this client call transcript, extract a clear list of concrete next steps and action items. Organize as: (1) Short-term — before or on the next call. (2) Long-term goals. Note who is responsible where mentioned.\n\nTranscript:\n{{transcript}}',
 true, 2),
('Questions for Stakeholders',
 'Based on the next steps and discussion in this transcript, write precise questions to address on the next call. For each next step or open item, write 1-3 targeted questions. Group by topic.\n\nTranscript:\n{{transcript}}',
 true, 3),
('Email Summary (1-pager)',
 'Write a concise 1-page email summary of this client call for all participants. Include: date/context, key decisions, agreed next steps, open questions. Professional tone.\n\nTranscript:\n{{transcript}}',
 true, 4),
('Email Follow-up (pre-next-call)',
 'Write a follow-up email to send before the next call. Remind participants of agreed next steps, highlight items needing preparation, confirm the next session agenda. Concise and action-oriented.\n\nTranscript:\n{{transcript}}',
 true, 5),
('Next Call Meeting Topics',
 'Generate a structured agenda for the next meeting based on this transcript. List main topics by priority. For each, include a 1-sentence description of what needs to be discussed or decided.\n\nTranscript:\n{{transcript}}',
 true, 6);
```

- [ ] **Step 4: Run seed.sql in Supabase SQL Editor**

Verify 6 rows in `artifact_types` with `is_default = true`.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-1] feat: Supabase schema and seed"
```

---

### Task 1.2: Backend skeleton

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/__init__.py`
- Create: `backend/api/__init__.py`
- Create: `backend/api/main.py`
- Create: `backend/database/__init__.py`
- Create: `backend/database/connection.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`
- Create: `.env` (local, gitignored)
- Create: `.env.example`

- [ ] **Step 1: Write backend/requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.1
supabase==2.4.6
anthropic==0.26.0
python-multipart==0.0.9
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

- [ ] **Step 2: Write .env.example**

```bash
# Backend (Railway + local)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
FRONTEND_URL=http://localhost:3000
LOG_LEVEL=INFO

# Frontend (Vercel + local)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_BACKEND_URL=http://localhost:8001
NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL=http://localhost:8000
```

Copy `.env.example` to `.env` and fill in real Supabase values from the Supabase dashboard (Settings → API).

- [ ] **Step 3: Write backend/database/connection.py**

```python
# backend/database/connection.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"]
        )
    return _client
```

- [ ] **Step 4: Write backend/api/main.py**

```python
# backend/api/main.py
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("call_tracker")

app = FastAPI(title="Call Tracker API")

origins = os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write failing test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 6: Run test — expect PASS**

```bash
cd backend && pip install -r requirements.txt && pytest tests/test_health.py -v
```
Expected: `PASSED`

- [ ] **Step 7: Start backend and verify in browser**

```bash
cd backend && uvicorn api.main:app --reload --port 8001
```
Open `http://localhost:8001/health` → should return `{"status":"ok"}`

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-1] feat: FastAPI skeleton with health endpoint"
```

---

### Task 1.3: Frontend skeleton

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/page.tsx`
- Create: `frontend/.env.local`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Create frontend/.env.local**

```bash
NEXT_PUBLIC_BACKEND_URL=http://localhost:8001
NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

Fill in Supabase values from dashboard.

- [ ] **Step 2: Install TailwindCSS if not present**

```bash
cd frontend && npm install && npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

Update `tailwind.config.js`:
```js
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './src/**/*.{ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

Update `frontend/app/globals.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 3: Write frontend/app/layout.tsx**

```tsx
// frontend/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = { title: 'Call Tracker' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center justify-between shadow-sm">
          <a href="/" className="font-semibold text-gray-900 text-lg">Call Tracker</a>
          <div id="status-area" />
        </nav>
        <main className="p-6 max-w-5xl mx-auto">{children}</main>
      </body>
    </html>
  )
}
```

- [ ] **Step 4: Write frontend/app/page.tsx (placeholder)**

```tsx
// frontend/app/page.tsx
export default function Home() {
  return (
    <div className="text-center py-20 text-gray-400">
      Loading projects...
    </div>
  )
}
```

- [ ] **Step 5: Start frontend and verify in browser**

```bash
cd frontend && npm run dev
```
Open `http://localhost:3000` → see "Call Tracker" nav bar and "Loading projects..." text.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-1] feat: Next.js skeleton with layout"
```

---

## Slice 2: Create and List Projects

**What you see at the end:** Projects page with a "New Project" button. Click it, fill in a name, hit create — project card appears instantly. Refresh — it's still there (persisted in Supabase).

---

### Task 2.1: Projects API

**Files:**
- Create: `backend/api/models.py`
- Create: `backend/api/routes/__init__.py`
- Create: `backend/api/routes/projects.py`
- Create: `backend/tests/test_projects.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Write backend/api/models.py**

```python
# backend/api/models.py
from pydantic import BaseModel
from typing import Optional

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    created_at: str
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_projects.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

MOCK = {"id": "aaa", "name": "FactSet Q1", "description": None, "created_at": "2026-04-09T10:00:00+00:00"}

@pytest.mark.asyncio
async def test_list_projects():
    with patch("backend.api.routes.projects.get_client") as m:
        m.return_value.table.return_value.select.return_value.order.return_value.execute.return_value.data = [MOCK]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/projects")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "FactSet Q1"

@pytest.mark.asyncio
async def test_create_project():
    with patch("backend.api.routes.projects.get_client") as m:
        m.return_value.table.return_value.insert.return_value.execute.return_value.data = [MOCK]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/projects", json={"name": "FactSet Q1"})
    assert r.status_code == 201
    assert r.json()["name"] == "FactSet Q1"
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_projects.py -v
```

- [ ] **Step 4: Write backend/api/routes/projects.py**

```python
# backend/api/routes/projects.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import ProjectCreate, ProjectResponse
from backend.database.connection import get_client

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger("call_tracker.projects")

@router.get("", response_model=list[ProjectResponse])
async def list_projects():
    logger.info("📥 GET /api/projects")
    db = get_client()
    result = db.table("projects").select("*").order("created_at", desc=True).execute()
    return result.data

@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(payload: ProjectCreate):
    logger.info(f"📥 POST /api/projects name={payload.name}")
    db = get_client()
    result = db.table("projects").insert(payload.model_dump()).execute()
    logger.info(f"✅ Created project {result.data[0]['id']}")
    return result.data[0]

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    db = get_client()
    result = db.table("projects").select("*").eq("id", project_id).execute()
    if not result.data:
        raise HTTPException(404, "Project not found")
    return result.data[0]

@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    db = get_client()
    db.table("projects").delete().eq("id", project_id).execute()
    logger.info(f"✅ Deleted project {project_id}")
```

- [ ] **Step 5: Register router in main.py**

Add after the health endpoint:
```python
from backend.api.routes import projects
app.include_router(projects.router)
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_projects.py -v
```
Expected: 2 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-2] feat: projects CRUD API"
```

---

### Task 2.2: Project list UI

**Files:**
- Create: `frontend/src/api/backend.ts`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/components/projects/ProjectList.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Write frontend/src/types/index.ts**

```typescript
// frontend/src/types/index.ts
export type KanbanStage = 'transcript' | 'artifacts' | 'topics' | 'done'
export type TopicStatus = 'active' | 'decision_made' | 'on_hold' | 'closed'
export type ArtifactStatus = 'pending' | 'generating' | 'done' | 'error'
export type ArtifactMode = 'claude' | 'manual'

export interface Project {
  id: string
  name: string
  description?: string
  created_at: string
}

export interface Call {
  id: string
  project_id: string
  title: string
  mp3_filename?: string
  transcript_text?: string
  kanban_stage: KanbanStage
  created_at: string
  updated_at: string
}

export interface ArtifactType {
  id: string
  project_id?: string
  name: string
  prompt: string
  is_default: boolean
  sort_order: number
}

export interface Artifact {
  id: string
  call_id: string
  artifact_type_id: string
  prompt_used: string
  content?: string
  mode: ArtifactMode
  status: ArtifactStatus
  error_message?: string
  created_at: string
  updated_at: string
}

export interface Topic {
  id: string
  project_id: string
  title: string
  status: TopicStatus
  first_call_id?: string
  created_at: string
  updated_at: string
}

export interface ArtifactSSEEvent {
  type: 'update' | 'done'
  artifact_id?: string
  status?: ArtifactStatus
  content?: string
  error_message?: string
}
```

- [ ] **Step 2: Write frontend/src/api/backend.ts**

```typescript
// frontend/src/api/backend.ts
import type { Project, Call, ArtifactType, Artifact, Topic, KanbanStage } from '@/types'

const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  projects: {
    list: () => request<Project[]>('/api/projects'),
    create: (data: { name: string; description?: string }) =>
      request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
    get: (id: string) => request<Project>(`/api/projects/${id}`),
    delete: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  },
  calls: {
    list: (projectId: string) => request<Call[]>(`/api/projects/${projectId}/calls`),
    create: (projectId: string, data: { title: string }) =>
      request<Call>(`/api/projects/${projectId}/calls`, { method: 'POST', body: JSON.stringify(data) }),
    get: (id: string) => request<Call>(`/api/calls/${id}`),
    update: (id: string, data: Partial<Pick<Call, 'transcript_text' | 'mp3_filename'>>) =>
      request<Call>(`/api/calls/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    advanceStage: (id: string, stage: KanbanStage) =>
      request<Call>(`/api/calls/${id}/stage`, { method: 'PATCH', body: JSON.stringify({ stage }) }),
  },
  artifactTypes: {
    list: () => request<ArtifactType[]>('/api/artifact-types'),
    create: (data: { name: string; prompt: string }) =>
      request<ArtifactType>('/api/artifact-types', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { name?: string; prompt?: string }) =>
      request<ArtifactType>(`/api/artifact-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/api/artifact-types/${id}`, { method: 'DELETE' }),
  },
  artifacts: {
    list: (callId: string) => request<Artifact[]>(`/api/calls/${callId}/artifacts`),
    generate: (callId: string, configs: { artifact_type_id: string; mode: string }[]) =>
      request<{ artifact_ids: string[] }>(`/api/calls/${callId}/artifacts/generate`, {
        method: 'POST', body: JSON.stringify({ artifact_configs: configs }),
      }),
    streamUrl: (callId: string) => `${BASE}/api/calls/${callId}/artifacts/stream`,
    update: (id: string, content: string) =>
      request<Artifact>(`/api/artifacts/${id}`, { method: 'PATCH', body: JSON.stringify({ content }) }),
    markDone: (id: string) =>
      request<Artifact>(`/api/artifacts/${id}/done`, { method: 'PATCH' }),
  },
  topics: {
    list: (projectId: string) => request<Topic[]>(`/api/projects/${projectId}/topics`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<Topic>(`/api/projects/${projectId}/topics`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { title?: string; status?: string }) =>
      request<Topic>(`/api/topics/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/api/topics/${id}`, { method: 'DELETE' }),
    extract: (callId: string) =>
      request<{ topics: any[] }>(`/api/calls/${callId}/topics/extract`, { method: 'POST' }),
    validate: (callId: string, topic_updates: any[]) =>
      request<void>(`/api/calls/${callId}/topics/validate`, {
        method: 'POST', body: JSON.stringify({ topic_updates }),
      }),
  },
}
```

- [ ] **Step 3: Write frontend/src/components/projects/ProjectList.tsx**

```tsx
// frontend/src/components/projects/ProjectList.tsx
'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api } from '@/api/backend'
import type { Project } from '@/types'

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.projects.list()
      .then(setProjects)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      const p = await api.projects.create({ name: name.trim() })
      setProjects(prev => [p, ...prev])
      setName('')
      setShowForm(false)
    } catch (e: any) {
      setError(e.message)
    }
  }

  if (loading) return <div className="text-gray-400 text-center py-20">Loading...</div>

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <button
          onClick={() => setShowForm(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          + New Project
        </button>
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {showForm && (
        <form onSubmit={handleCreate} className="mb-6 p-4 bg-white border rounded-xl shadow-sm">
          <label className="block text-sm font-medium text-gray-700 mb-1">Project name</label>
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. FactSet Q1 2026"
            className="w-full border rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <div className="flex gap-2">
            <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Create</button>
            <button type="button" onClick={() => { setShowForm(false); setName('') }} className="border px-4 py-2 rounded-lg text-sm text-gray-600">Cancel</button>
          </div>
        </form>
      )}

      {projects.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg mb-2">No projects yet</p>
          <p className="text-sm">Create your first project to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map(p => (
            <Link key={p.id} href={`/projects/${p.id}`}
              className="block p-4 bg-white border rounded-xl shadow-sm hover:border-blue-400 hover:shadow-md transition-all">
              <div className="font-medium text-gray-900">{p.name}</div>
              {p.description && <div className="text-sm text-gray-500 mt-0.5">{p.description}</div>}
              <div className="text-xs text-gray-400 mt-1">{new Date(p.created_at).toLocaleDateString()}</div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Update app/page.tsx**

```tsx
// frontend/app/page.tsx
import ProjectList from '@/components/projects/ProjectList'
export default function Home() { return <ProjectList /> }
```

- [ ] **Step 5: Test in browser**

With both servers running:
1. Open `http://localhost:3000`
2. Click "New Project" → fill in a name → Create
3. Project card appears immediately
4. Refresh page → project still there (Supabase persisted)

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-2] feat: project list UI — create and list projects"
```

---

## Slice 3: Kanban Board Layout

**What you see at the end:** Click a project → see 4 kanban columns (Get Transcript / Artifacts / Topics / Done ✓). Columns are empty but correctly laid out. "New Call" button visible in the first column.

---

### Task 3.1: Calls list API

**Files:**
- Create: `backend/api/routes/calls.py`
- Create: `backend/tests/test_calls.py`
- Modify: `backend/api/models.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add call models to models.py**

```python
# Add to backend/api/models.py
from typing import Literal

KanbanStage = Literal["transcript", "artifacts", "topics", "done"]

class CallCreate(BaseModel):
    title: str

class CallStageUpdate(BaseModel):
    stage: KanbanStage

class CallUpdate(BaseModel):
    transcript_text: Optional[str] = None
    mp3_filename: Optional[str] = None

class CallResponse(BaseModel):
    id: str
    project_id: str
    title: str
    mp3_filename: Optional[str]
    transcript_text: Optional[str]
    kanban_stage: str
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_calls.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

PID = "pid-111"
CID = "cid-222"
MOCK_CALL = {
    "id": CID, "project_id": PID, "title": "2026-04-09",
    "mp3_filename": None, "transcript_text": None, "kanban_stage": "transcript",
    "created_at": "2026-04-09T10:00:00+00:00", "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_list_calls():
    with patch("backend.api.routes.calls.get_client") as m:
        m.return_value.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [MOCK_CALL]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/projects/{PID}/calls")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "2026-04-09"

@pytest.mark.asyncio
async def test_create_call_no_active():
    with patch("backend.api.routes.calls.get_client") as m:
        m.return_value.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
        m.return_value.table.return_value.insert.return_value.execute.return_value.data = [MOCK_CALL]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/projects/{PID}/calls", json={"title": "2026-04-09"})
    assert r.status_code == 201

@pytest.mark.asyncio
async def test_create_call_blocked_if_active():
    with patch("backend.api.routes.calls.get_client") as m:
        m.return_value.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [MOCK_CALL]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/projects/{PID}/calls", json={"title": "2026-04-09"})
    assert r.status_code == 409
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_calls.py -v
```

- [ ] **Step 4: Write backend/api/routes/calls.py**

```python
# backend/api/routes/calls.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import CallCreate, CallStageUpdate, CallUpdate, CallResponse
from backend.database.connection import get_client

router = APIRouter(tags=["calls"])
logger = logging.getLogger("call_tracker.calls")

@router.get("/api/projects/{project_id}/calls", response_model=list[CallResponse])
async def list_calls(project_id: str):
    db = get_client()
    result = db.table("calls").select("*").eq("project_id", project_id).order("created_at").execute()
    return result.data

@router.post("/api/projects/{project_id}/calls", response_model=CallResponse, status_code=201)
async def create_call(project_id: str, payload: CallCreate):
    logger.info(f"📥 POST /api/projects/{project_id}/calls title={payload.title}")
    db = get_client()
    active = db.table("calls").select("id").eq("project_id", project_id).neq("kanban_stage", "done").execute()
    if active.data:
        raise HTTPException(409, "Complete the current call before creating a new one")
    result = db.table("calls").insert({"project_id": project_id, "title": payload.title}).execute()
    logger.info(f"✅ Created call {result.data[0]['id']}")
    return result.data[0]

@router.get("/api/calls/{call_id}", response_model=CallResponse)
async def get_call(call_id: str):
    db = get_client()
    result = db.table("calls").select("*").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(404, "Call not found")
    return result.data[0]

@router.patch("/api/calls/{call_id}", response_model=CallResponse)
async def update_call(call_id: str, payload: CallUpdate):
    db = get_client()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = db.table("calls").update(updates).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(404, "Call not found")
    return result.data[0]

@router.patch("/api/calls/{call_id}/stage", response_model=CallResponse)
async def update_stage(call_id: str, payload: CallStageUpdate):
    logger.info(f"📥 PATCH /api/calls/{call_id}/stage → {payload.stage}")
    db = get_client()
    result = db.table("calls").update({"kanban_stage": payload.stage}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(404, "Call not found")
    logger.info(f"✅ Call {call_id} → {payload.stage}")
    return result.data[0]
```

- [ ] **Step 5: Register router and run tests**

Add to `main.py`: `from backend.api.routes import calls` + `app.include_router(calls.router)`

```bash
cd backend && pytest tests/test_calls.py -v
```
Expected: 3 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-3] feat: calls list + create + stage API"
```

---

### Task 3.2: Kanban board UI

**Files:**
- Create: `frontend/app/projects/[id]/page.tsx`
- Create: `frontend/src/components/kanban/KanbanBoard.tsx`

- [ ] **Step 1: Write KanbanBoard.tsx**

```tsx
// frontend/src/components/kanban/KanbanBoard.tsx
import Link from 'next/link'
import type { Call, KanbanStage } from '@/types'

const COLUMNS: { key: KanbanStage; label: string; color: string }[] = [
  { key: 'transcript', label: 'Get Transcript', color: 'border-t-gray-400' },
  { key: 'artifacts', label: 'Artifacts', color: 'border-t-blue-400' },
  { key: 'topics', label: 'Topics', color: 'border-t-purple-400' },
  { key: 'done', label: 'Done ✓', color: 'border-t-green-400' },
]

interface Props {
  projectId: string
  calls: Call[]
  activeCallExists: boolean
  onNewCall: () => void
}

export default function KanbanBoard({ projectId, calls, activeCallExists, onNewCall }: Props) {
  return (
    <div className="grid grid-cols-4 gap-4">
      {COLUMNS.map(col => {
        const colCalls = calls.filter(c => c.kanban_stage === col.key)
        return (
          <div key={col.key} className={`bg-gray-100 rounded-xl p-3 border-t-4 ${col.color}`}>
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold text-sm text-gray-700">{col.label}</h3>
              <span className="text-xs text-gray-400 bg-white rounded-full px-2 py-0.5">{colCalls.length}</span>
            </div>

            <div className="space-y-2 min-h-24">
              {colCalls.map(call => (
                <Link key={call.id} href={`/projects/${projectId}/calls/${call.id}`}>
                  <div className="bg-white rounded-lg p-3 shadow-sm hover:shadow-md hover:border-blue-300 border border-transparent transition-all cursor-pointer">
                    <div className="font-medium text-sm text-gray-900">{call.title}</div>
                    <div className="text-xs text-gray-400 mt-1">
                      {new Date(call.created_at).toLocaleDateString()}
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            {col.key === 'transcript' && (
              <button
                onClick={onNewCall}
                disabled={activeCallExists}
                title={activeCallExists ? 'Complete the current call first' : 'Create new call'}
                className="mt-2 w-full border-2 border-dashed border-gray-300 rounded-lg py-2 text-sm text-gray-400 hover:border-blue-400 hover:text-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                + New Call
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Write app/projects/[id]/page.tsx**

```tsx
// frontend/app/projects/[id]/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import KanbanBoard from '@/components/kanban/KanbanBoard'
import { api } from '@/api/backend'
import type { Project, Call } from '@/types'

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<Project | null>(null)
  const [calls, setCalls] = useState<Call[]>([])
  const [tab, setTab] = useState<'kanban' | 'topics'>('kanban')
  const [showNewCallForm, setShowNewCallForm] = useState(false)
  const [newCallTitle, setNewCallTitle] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api.projects.get(id).then(setProject)
    api.calls.list(id).then(setCalls)
  }, [id])

  const activeCallExists = calls.some(c => c.kanban_stage !== 'done')

  async function handleCreateCall(e: React.FormEvent) {
    e.preventDefault()
    if (!newCallTitle.trim()) return
    try {
      const call = await api.calls.create(id, { title: newCallTitle.trim() })
      setCalls(prev => [...prev, call])
      setNewCallTitle('')
      setShowNewCallForm(false)
    } catch (e: any) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-6 text-sm text-gray-500">
        <a href="/" className="hover:text-blue-600">← Projects</a>
        <span>/</span>
        <span className="font-medium text-gray-900">{project?.name}</span>
      </div>

      <div className="flex gap-6 border-b mb-6">
        {(['kanban', 'topics'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`pb-3 text-sm font-medium capitalize transition-colors ${tab === t ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}>
            {t === 'kanban' ? '📋 Kanban Board' : '🗂 Topic Dashboard'}
          </button>
        ))}
      </div>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {tab === 'kanban' && (
        <>
          {showNewCallForm && (
            <form onSubmit={handleCreateCall} className="mb-4 p-4 bg-white border rounded-xl shadow-sm max-w-sm">
              <label className="block text-sm font-medium text-gray-700 mb-1">Call title</label>
              <input autoFocus value={newCallTitle} onChange={e => setNewCallTitle(e.target.value)}
                placeholder="e.g. 2026-04-09" className="w-full border rounded-lg px-3 py-2 text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-blue-500" />
              <div className="flex gap-2">
                <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Create</button>
                <button type="button" onClick={() => setShowNewCallForm(false)} className="border px-4 py-2 rounded-lg text-sm text-gray-600">Cancel</button>
              </div>
            </form>
          )}
          <KanbanBoard projectId={id} calls={calls} activeCallExists={activeCallExists} onNewCall={() => setShowNewCallForm(true)} />
        </>
      )}

      {tab === 'topics' && (
        <div className="text-gray-400 text-center py-20">Topic Dashboard — coming in Slice 9</div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Test in browser**

1. Click a project → see 4 kanban columns
2. "New Call" button in first column — click it, fill in a date title, create
3. Card appears in "Get Transcript" column
4. Try creating a second call → button disabled with tooltip

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-3] feat: kanban board with call creation"
```

---

## Slice 4: Get Transcript — Load MP3 or TXT

**What you see at the end:** Click a call card → see the call detail page at "Get Transcript" stage. Drop or select an MP3 or .txt file. If .txt → transcript stored, card moves to "Artifacts". If MP3 → transcription runs locally, same result.

---

### Task 4.1: Transcription status badge + local server skeleton

**Files:**
- Create: `frontend/src/api/local.ts`
- Create: `frontend/src/components/ui/TranscriptionStatusBadge.tsx`
- Modify: `frontend/app/layout.tsx`
- Create: `transcription/server.py`
- Create: `transcription/transcribe.py`
- Create: `transcription/requirements.txt`
- Create: `transcription/run_transcription.sh`
- Create: `transcription/setup.sh`

- [ ] **Step 1: Write frontend/src/api/local.ts**

```typescript
// frontend/src/api/local.ts
const LOCAL = process.env.NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL || 'http://localhost:8000'

export async function checkTranscriptionHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${LOCAL}/health`, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch { return false }
}

export async function transcribeAudio(file: File): Promise<{ transcript_text: string; duration: number; speakers: string[] }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${LOCAL}/transcribe`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Transcription failed')
  }
  return res.json()
}
```

- [ ] **Step 2: Write TranscriptionStatusBadge.tsx**

```tsx
// frontend/src/components/ui/TranscriptionStatusBadge.tsx
'use client'
import { useEffect, useState } from 'react'
import { checkTranscriptionHealth } from '@/api/local'

export default function TranscriptionStatusBadge() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    const check = async () => setOnline(await checkTranscriptionHealth())
    check()
    const id = setInterval(check, 30000)
    return () => clearInterval(id)
  }, [])

  if (online === null) return null

  return (
    <div className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${online ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-green-500' : 'bg-amber-500'}`} />
      Transcription {online ? 'Online' : 'Offline'}
    </div>
  )
}
```

- [ ] **Step 3: Add badge to layout.tsx**

Replace `<div id="status-area" />` in `layout.tsx`:
```tsx
import TranscriptionStatusBadge from '@/components/ui/TranscriptionStatusBadge'
// ...
<TranscriptionStatusBadge />
```

- [ ] **Step 4: Write transcription/requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
python-dotenv==1.0.1
openai-whisper==20231117
pyannote.audio==3.1.1
torch==2.2.2
torchaudio==2.2.2
```

- [ ] **Step 5: Write transcription/transcribe.py (port of transcribe_watcher.py)**

```python
# transcription/transcribe.py
"""
Replicates /Users/louisgarnier/Claude/PM/transcribe_watcher.py 100%.
Whisper (medium) + pyannote speaker diarization.
"""
import os
import logging
from pathlib import Path
from datetime import timedelta
import whisper
from pyannote.audio import Pipeline

logger = logging.getLogger("transcription")
_whisper_model = None
_pipeline = None

def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        logger.info("🚀 Loading Whisper medium model...")
        _whisper_model = whisper.load_model("medium")
        logger.info("✅ Whisper loaded")
    return _whisper_model

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        token = os.environ.get("HUGGINGFACE_TOKEN")
        logger.info("🚀 Loading pyannote pipeline...")
        _pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
        logger.info("✅ Pyannote loaded")
    return _pipeline

def _dominant_speaker(diarization, start: float, end: float) -> str:
    best, best_overlap = "SPEAKER_0", 0.0
    for turn, _, spk in diarization.itertracks(yield_label=True):
        overlap = min(turn.end, end) - max(turn.start, start)
        if overlap > best_overlap:
            best_overlap, best = overlap, spk
    return best

def transcribe_audio(audio_path: str, filename: str) -> dict:
    logger.info(f"📥 Transcribing {filename}...")
    model = get_whisper()
    pipeline = get_pipeline()

    result = model.transcribe(audio_path, word_timestamps=False)
    segments = result["segments"]
    duration = result.get("duration", 0)

    diarization = pipeline(audio_path)

    lines = [
        f"Transcript: {Path(filename).stem}",
        f"Duration: {str(timedelta(seconds=int(duration)))}",
        ""
    ]
    speakers = set()
    for seg in segments:
        spk = _dominant_speaker(diarization, seg["start"], seg["end"])
        speakers.add(spk)
        ts = str(timedelta(seconds=int(seg["start"])))[2:]  # MM:SS
        lines.append(f"[{ts}] {spk}: {seg['text'].strip()}")

    transcript_text = "\n".join(lines)
    logger.info(f"✅ Done — {len(segments)} segments, {len(speakers)} speakers")
    return {"transcript_text": transcript_text, "duration": duration, "speakers": list(speakers)}
```

- [ ] **Step 6: Write transcription/server.py**

```python
# transcription/server.py
import os
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [transcription] %(levelname)s: %(message)s")
logger = logging.getLogger("transcription.server")

app = FastAPI(title="Call Tracker — Local Transcription")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.filename.endswith(".mp3"):
        raise HTTPException(400, "Only .mp3 files supported")
    logger.info(f"📥 /transcribe — {file.filename}")
    from transcribe import transcribe_audio
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = transcribe_audio(tmp_path, file.filename)
        return result
    except Exception as e:
        logger.error(f"❌ {e}")
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 7: Write transcription/run_transcription.sh**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate
echo "🚀 Starting transcription server on port 8000..."
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

```bash
chmod +x transcription/run_transcription.sh
```

- [ ] **Step 8: Verify badge in browser**

With frontend running: badge shows "Transcription Offline" (expected — server not running yet).
Start `./transcription/run_transcription.sh` → badge turns green within 30s.

- [ ] **Step 9: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-4] feat: transcription badge + local server + transcribe.py"
```

---

### Task 4.2: Call detail page — Transcript stage

**Files:**
- Create: `frontend/app/projects/[id]/calls/[callId]/page.tsx`
- Create: `frontend/src/components/call/StageIndicator.tsx`
- Create: `frontend/src/components/call/TranscriptStage.tsx`

- [ ] **Step 1: Write StageIndicator.tsx**

```tsx
// frontend/src/components/call/StageIndicator.tsx
import type { KanbanStage } from '@/types'

const STAGES: { key: KanbanStage; label: string }[] = [
  { key: 'transcript', label: 'Transcript' },
  { key: 'artifacts', label: 'Artifacts' },
  { key: 'topics', label: 'Topics' },
  { key: 'done', label: 'Done' },
]

export default function StageIndicator({ current }: { current: KanbanStage }) {
  const idx = STAGES.findIndex(s => s.key === current)
  return (
    <div className="flex items-center gap-1 mb-8">
      {STAGES.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold
            ${i < idx ? 'bg-green-500 text-white' : i === idx ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-400'}`}>
            {i < idx ? '✓' : i + 1}
          </div>
          <span className={`text-sm ${i === idx ? 'font-semibold text-gray-900' : 'text-gray-400'}`}>{s.label}</span>
          {i < STAGES.length - 1 && <div className="w-8 h-px bg-gray-300 mx-1" />}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Write TranscriptStage.tsx**

```tsx
// frontend/src/components/call/TranscriptStage.tsx
'use client'
import { useState } from 'react'
import { api } from '@/api/backend'
import { transcribeAudio, checkTranscriptionHealth } from '@/api/local'

interface Props {
  callId: string
  onDone: () => void
}

export default function TranscriptStage({ callId, onDone }: Props) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [showOfflineModal, setShowOfflineModal] = useState(false)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setStatus('loading')
    setErrorMsg('')

    try {
      if (file.name.endsWith('.mp3')) {
        const online = await checkTranscriptionHealth()
        if (!online) { setStatus('idle'); setShowOfflineModal(true); return }
        const { transcript_text } = await transcribeAudio(file)
        await api.calls.update(callId, { transcript_text, mp3_filename: file.name })
      } else if (file.name.endsWith('.txt')) {
        const transcript_text = await file.text()
        await api.calls.update(callId, { transcript_text })
      } else {
        throw new Error('Please select an .mp3 or .txt file')
      }
      await api.calls.advanceStage(callId, 'artifacts')
      onDone()
    } catch (e: any) {
      setErrorMsg(e.message)
      setStatus('error')
    }
  }

  return (
    <div className="text-center py-16">
      <div className="text-4xl mb-4">🎙️</div>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">Load Call Transcript</h2>
      <p className="text-gray-500 text-sm mb-8">Drop an MP3 to transcribe locally, or a TXT if you already have the transcript</p>

      <label className={`inline-flex items-center gap-2 px-6 py-3 rounded-xl font-medium cursor-pointer transition-all
        ${status === 'loading' ? 'bg-gray-100 text-gray-400 cursor-wait' : 'bg-blue-600 text-white hover:bg-blue-700'}`}>
        {status === 'loading' ? '⏳ Processing...' : '📁 Select MP3 or TXT'}
        <input type="file" accept=".mp3,.txt" className="hidden" onChange={handleFile} disabled={status === 'loading'} />
      </label>

      {errorMsg && <p className="text-red-600 text-sm mt-4">{errorMsg}</p>}

      <p className="text-xs text-gray-400 mt-4">
        MP3 requires the local transcription server to be running
      </p>

      {showOfflineModal && <OfflineModal onClose={() => setShowOfflineModal(false)} />}
    </div>
  )
}

function OfflineModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 max-w-sm w-full mx-4 shadow-xl">
        <h3 className="font-semibold text-lg mb-3">⚠️ Transcription server offline</h3>
        <p className="text-sm text-gray-600 mb-4">To transcribe MP3 files, start the local server:</p>
        <ol className="text-sm space-y-2 mb-4 text-gray-700">
          <li>1. Open a new terminal tab</li>
          <li>2. Navigate to the Call Tracker folder</li>
          <li>3. Run: <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono text-xs">./transcription/run_transcription.sh</code></li>
        </ol>
        <p className="text-sm text-gray-500 mb-4">Or select a <strong>.txt</strong> transcript file instead.</p>
        <button onClick={onClose} className="w-full bg-blue-600 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700">Got it</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Write call detail page**

```tsx
// frontend/app/projects/[id]/calls/[callId]/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/api/backend'
import StageIndicator from '@/components/call/StageIndicator'
import TranscriptStage from '@/components/call/TranscriptStage'
import type { Call } from '@/types'

export default function CallDetailPage() {
  const { id: projectId, callId } = useParams<{ id: string; callId: string }>()
  const [call, setCall] = useState<Call | null>(null)

  async function reload() {
    const c = await api.calls.get(callId)
    setCall(c)
  }

  useEffect(() => { reload() }, [callId])

  if (!call) return <div className="text-gray-400 text-center py-20">Loading...</div>

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-6 text-sm text-gray-500">
        <a href={`/projects/${projectId}`} className="hover:text-blue-600">← {projectId}</a>
        <span>/</span>
        <span className="font-medium text-gray-900">{call.title}</span>
      </div>

      <StageIndicator current={call.kanban_stage} />

      {call.kanban_stage === 'transcript' && (
        <TranscriptStage callId={callId} onDone={reload} />
      )}

      {call.kanban_stage === 'artifacts' && (
        <div className="text-center py-20 text-gray-400">Artifacts stage — coming in Slice 5</div>
      )}

      {call.kanban_stage === 'topics' && (
        <div className="text-center py-20 text-gray-400">Topics stage — coming in Slice 7</div>
      )}

      {call.kanban_stage === 'done' && (
        <div className="text-center py-20">
          <div className="text-5xl mb-4">✅</div>
          <p className="text-xl font-semibold text-green-700">Call complete</p>
          <a href={`/projects/${projectId}`} className="text-blue-600 text-sm hover:underline mt-3 block">← Back to project</a>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Test in browser**

1. Click a call card in the kanban
2. See the stage indicator at "Transcript"
3. Select a `.txt` file → loading briefly → card advances to "Artifacts" column on the kanban
4. Go back to kanban → card is now in "Artifacts" column

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-4] feat: transcript stage UI — MP3/TXT upload, offline modal"
```

---

## Slice 5: Artifacts — Select, Generate, Review

**What you see at the end:** At the Artifacts stage, see the 6 artifact types. Set each to Claude/Manual/Skip. Click Generate — watch each artifact appear live with a status indicator. Edit content inline. Mark all done — button to advance to Topics appears.

---

### Task 5.1: Artifact types API + artifacts generation API

**Files:**
- Create: `backend/api/routes/artifact_types.py`
- Create: `backend/api/routes/artifacts.py`
- Create: `backend/services/__init__.py`
- Create: `backend/services/claude_service.py`
- Create: `backend/tests/test_artifacts.py`
- Modify: `backend/api/models.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add models to models.py**

```python
# Add to backend/api/models.py
class ArtifactTypeCreate(BaseModel):
    name: str
    prompt: str
    project_id: Optional[str] = None

class ArtifactTypeUpdate(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None

class ArtifactTypeResponse(BaseModel):
    id: str
    project_id: Optional[str]
    name: str
    prompt: str
    is_default: bool
    sort_order: int
    created_at: str
    updated_at: str

class ArtifactConfig(BaseModel):
    artifact_type_id: str
    mode: Literal["claude", "manual"]

class ArtifactGenerateRequest(BaseModel):
    artifact_configs: list[ArtifactConfig]

class ArtifactUpdate(BaseModel):
    content: str

class ArtifactResponse(BaseModel):
    id: str
    call_id: str
    artifact_type_id: str
    prompt_used: str
    content: Optional[str]
    mode: str
    status: str
    error_message: Optional[str]
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Write backend/services/claude_service.py**

```python
# backend/services/claude_service.py
import os
import re
import json
import logging
from anthropic import AsyncAnthropic

logger = logging.getLogger("call_tracker.claude")
_client: AsyncAnthropic | None = None
MODEL = "claude-sonnet-4-6"

def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client

async def generate_artifact(prompt_template: str, transcript: str) -> str:
    prompt = prompt_template.replace("{{transcript}}", transcript)
    logger.info(f"🚀 Claude artifact — model={MODEL} prompt_len={len(prompt)}")
    msg = await get_client().messages.create(
        model=MODEL, max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    content = msg.content[0].text
    logger.info(f"✅ Artifact done — len={len(content)}")
    return content

async def extract_topics(transcript: str, existing_topics: list[dict], call_number: int) -> list[dict]:
    if call_number == 1:
        prompt = f"""Analyze this client call transcript. Extract the key recurring topics, themes, and items needing follow-up.

For each topic return:
- title: short name (5 words max)
- summary: what happened in this call (2-3 sentences)
- follow_up_items: list of specific follow-up actions

Return ONLY a JSON array: [{{"title":"...","summary":"...","follow_up_items":["..."]}}]

Transcript:
{transcript}"""
    else:
        existing_str = "\n".join(f"- {t['title']}" for t in existing_topics)
        prompt = f"""Review this new client call transcript. Existing tracked topics:
{existing_str}

For each existing topic: did it come up? If yes, provide updated summary and new follow-up items.
Also identify any NEW topics not in the list.

Return ONLY a JSON array for ALL topics (updated + new):
[{{"title":"...","summary":"...","follow_up_items":["..."],"is_new":true/false}}]

Transcript:
{transcript}"""

    logger.info(f"🚀 Claude topics — call_number={call_number} existing={len(existing_topics)}")
    msg = await get_client().messages.create(
        model=MODEL, max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned no JSON array: {text[:200]}")
    topics = json.loads(match.group())
    logger.info(f"✅ Topics extracted — count={len(topics)}")
    return topics
```

- [ ] **Step 3: Write failing test**

```python
# backend/tests/test_artifacts.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

CID = "cid-222"
AID = "aid-333"
TID = "tid-444"
MOCK_ARTIFACT = {
    "id": AID, "call_id": CID, "artifact_type_id": TID,
    "prompt_used": "Summarize...", "content": None,
    "mode": "claude", "status": "pending", "error_message": None,
    "created_at": "2026-04-09T10:00:00+00:00", "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_mark_artifact_done():
    with patch("backend.api.routes.artifacts.get_client") as m:
        done = {**MOCK_ARTIFACT, "status": "done"}
        m.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [done]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(f"/api/artifacts/{AID}/done")
    assert r.status_code == 200
    assert r.json()["status"] == "done"

@pytest.mark.asyncio
async def test_update_artifact_content():
    with patch("backend.api.routes.artifacts.get_client") as m:
        updated = {**MOCK_ARTIFACT, "content": "Some content"}
        m.return_value.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(f"/api/artifacts/{AID}", json={"content": "Some content"})
    assert r.status_code == 200
    assert r.json()["content"] == "Some content"
```

- [ ] **Step 4: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_artifacts.py -v
```

- [ ] **Step 5: Write backend/api/routes/artifact_types.py**

```python
# backend/api/routes/artifact_types.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import ArtifactTypeCreate, ArtifactTypeUpdate, ArtifactTypeResponse
from backend.database.connection import get_client

router = APIRouter(prefix="/api/artifact-types", tags=["artifact-types"])
logger = logging.getLogger("call_tracker.artifact_types")

@router.get("", response_model=list[ArtifactTypeResponse])
async def list_types():
    return get_client().table("artifact_types").select("*").order("sort_order").execute().data

@router.post("", response_model=ArtifactTypeResponse, status_code=201)
async def create_type(payload: ArtifactTypeCreate):
    result = get_client().table("artifact_types").insert({**payload.model_dump(), "is_default": False}).execute()
    return result.data[0]

@router.patch("/{type_id}", response_model=ArtifactTypeResponse)
async def update_type(type_id: str, payload: ArtifactTypeUpdate):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = get_client().table("artifact_types").update(updates).eq("id", type_id).execute()
    if not result.data:
        raise HTTPException(404, "Not found")
    return result.data[0]

@router.delete("/{type_id}", status_code=204)
async def delete_type(type_id: str):
    get_client().table("artifact_types").delete().eq("id", type_id).execute()
```

- [ ] **Step 6: Write backend/api/routes/artifacts.py**

```python
# backend/api/routes/artifacts.py
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from backend.api.models import ArtifactGenerateRequest, ArtifactUpdate, ArtifactResponse
from backend.database.connection import get_client
from backend.services.claude_service import generate_artifact

router = APIRouter(tags=["artifacts"])
logger = logging.getLogger("call_tracker.artifacts")

@router.get("/api/calls/{call_id}/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(call_id: str):
    return get_client().table("artifacts").select("*").eq("call_id", call_id).execute().data

@router.post("/api/calls/{call_id}/artifacts/generate")
async def start_generation(call_id: str, payload: ArtifactGenerateRequest):
    logger.info(f"📥 generate {len(payload.artifact_configs)} artifacts for call {call_id}")
    db = get_client()
    call = db.table("calls").select("transcript_text").eq("id", call_id).execute()
    if not call.data or not call.data[0].get("transcript_text"):
        raise HTTPException(400, "Call has no transcript")

    for config in payload.artifact_configs:
        atype = db.table("artifact_types").select("*").eq("id", config.artifact_type_id).execute()
        if not atype.data:
            raise HTTPException(404, f"Artifact type {config.artifact_type_id} not found")
        status = "pending" if config.mode == "claude" else "done"
        db.table("artifacts").insert({
            "call_id": call_id,
            "artifact_type_id": config.artifact_type_id,
            "prompt_used": atype.data[0]["prompt"],
            "mode": config.mode,
            "status": status,
        }).execute()

    logger.info(f"✅ Created artifact records for call {call_id}")
    return {"status": "ok"}

@router.get("/api/calls/{call_id}/artifacts/stream")
async def stream_generation(call_id: str):
    db = get_client()
    call = db.table("calls").select("transcript_text").eq("id", call_id).execute()
    if not call.data:
        raise HTTPException(404, "Call not found")
    transcript = call.data[0]["transcript_text"] or ""
    pending = db.table("artifacts").select("*, artifact_types(prompt)").eq("call_id", call_id).eq("mode", "claude").eq("status", "pending").execute()

    async def event_stream():
        tasks = [_generate_one(a, transcript, db) for a in pending.data]
        for coro in asyncio.as_completed(tasks):
            event = await coro
            yield f"data: {json.dumps(event)}\n\n"
        yield 'data: {"type":"done"}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")

async def _generate_one(artifact: dict, transcript: str, db) -> dict:
    aid = artifact["id"]
    db.table("artifacts").update({"status": "generating"}).eq("id", aid).execute()
    try:
        content = await generate_artifact(artifact["artifact_types"]["prompt"], transcript)
        db.table("artifacts").update({"status": "done", "content": content}).eq("id", aid).execute()
        return {"type": "update", "artifact_id": aid, "status": "done", "content": content}
    except Exception as e:
        logger.error(f"❌ Artifact {aid}: {e}")
        db.table("artifacts").update({"status": "error", "error_message": str(e)}).eq("id", aid).execute()
        return {"type": "update", "artifact_id": aid, "status": "error", "error_message": str(e)}

@router.patch("/api/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(artifact_id: str, payload: ArtifactUpdate):
    result = get_client().table("artifacts").update({"content": payload.content}).eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(404, "Not found")
    return result.data[0]

@router.patch("/api/artifacts/{artifact_id}/done", response_model=ArtifactResponse)
async def mark_done(artifact_id: str):
    result = get_client().table("artifacts").update({"status": "done"}).eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(404, "Not found")
    return result.data[0]
```

- [ ] **Step 7: Register routers in main.py**

```python
from backend.api.routes import artifact_types, artifacts
app.include_router(artifact_types.router)
app.include_router(artifacts.router)
```

- [ ] **Step 8: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_artifacts.py -v
```
Expected: 2 tests `PASSED`

- [ ] **Step 9: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-5] feat: artifact types + generation API + SSE"
```

---

### Task 5.2: Artifacts UI — selector, live generation, editor

**Files:**
- Create: `frontend/src/components/artifacts/ArtifactSelector.tsx`
- Create: `frontend/src/components/artifacts/ArtifactCard.tsx`
- Create: `frontend/src/components/artifacts/ArtifactsStage.tsx`
- Modify: `frontend/app/projects/[id]/calls/[callId]/page.tsx`

- [ ] **Step 1: Write ArtifactSelector.tsx**

```tsx
// frontend/src/components/artifacts/ArtifactSelector.tsx
import type { ArtifactType, ArtifactMode } from '@/types'

type Mode = ArtifactMode | 'excluded'

interface Config { artifact_type_id: string; mode: Mode }

interface Props {
  types: ArtifactType[]
  configs: Config[]
  onChange: (configs: Config[]) => void
}

const MODES: { key: Mode; label: string; style: string }[] = [
  { key: 'claude', label: '🤖 Claude', style: 'bg-blue-100 text-blue-700' },
  { key: 'manual', label: '✏️ Manual', style: 'bg-yellow-100 text-yellow-700' },
  { key: 'excluded', label: '✗ Skip', style: 'bg-gray-100 text-gray-500' },
]

export default function ArtifactSelector({ types, configs, onChange }: Props) {
  function setMode(typeId: string, mode: Mode) {
    onChange(configs.map(c => c.artifact_type_id === typeId ? { ...c, mode } : c))
  }

  return (
    <div className="space-y-2">
      {types.map(type => {
        const mode = configs.find(c => c.artifact_type_id === type.id)?.mode ?? 'excluded'
        return (
          <div key={type.id} className="flex items-center justify-between p-3 bg-white border rounded-xl">
            <span className="text-sm font-medium text-gray-800">{type.name}</span>
            <div className="flex gap-1">
              {MODES.map(m => (
                <button key={m.key} onClick={() => setMode(type.id, m.key)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${mode === m.key ? m.style : 'text-gray-400 hover:bg-gray-50'}`}>
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Write ArtifactCard.tsx**

```tsx
// frontend/src/components/artifacts/ArtifactCard.tsx
'use client'
import { useState } from 'react'
import { api } from '@/api/backend'
import type { Artifact, ArtifactType } from '@/types'

const STATUS = {
  pending:    { dot: 'bg-gray-400',  badge: 'bg-gray-100 text-gray-500',  label: 'Pending' },
  generating: { dot: 'bg-blue-500 animate-ping', badge: 'bg-blue-100 text-blue-600', label: 'Generating...' },
  done:       { dot: 'bg-green-500', badge: 'bg-green-100 text-green-700', label: 'Done' },
  error:      { dot: 'bg-red-500',   badge: 'bg-red-100 text-red-600',    label: 'Error' },
}

interface Props {
  artifact: Artifact
  type?: ArtifactType
  onUpdate: (a: Artifact) => void
}

export default function ArtifactCard({ artifact, type, onUpdate }: Props) {
  const [editing, setEditing] = useState(artifact.mode === 'manual' && !artifact.content)
  const [draft, setDraft] = useState(artifact.content || '')
  const s = STATUS[artifact.status]

  async function save() {
    const updated = await api.artifacts.update(artifact.id, draft)
    onUpdate(updated)
    setEditing(false)
  }

  async function markDone() {
    const updated = await api.artifacts.markDone(artifact.id)
    onUpdate(updated)
  }

  return (
    <div className="border rounded-xl p-4 bg-white shadow-sm">
      <div className="flex justify-between items-center mb-3">
        <h4 className="font-semibold text-sm text-gray-900">{type?.name ?? 'Artifact'}</h4>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full inline-block ${s.dot}`} />
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.badge}`}>{s.label}</span>
        </div>
      </div>

      {artifact.status === 'error' && (
        <p className="text-red-600 text-xs mb-2">⚠️ {artifact.error_message}</p>
      )}

      {editing ? (
        <>
          <textarea value={draft} onChange={e => setDraft(e.target.value)}
            placeholder="Paste or type content here..."
            className="w-full border rounded-lg p-3 text-sm resize-y min-h-36 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <div className="flex gap-2 mt-2">
            <button onClick={save} className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm">Save</button>
            <button onClick={() => setEditing(false)} className="border px-4 py-1.5 rounded-lg text-sm text-gray-600">Cancel</button>
          </div>
        </>
      ) : (
        <>
          <div className="text-sm text-gray-700 whitespace-pre-wrap max-h-48 overflow-y-auto">
            {artifact.content || <span className="text-gray-400 italic">No content yet</span>}
          </div>
          <div className="flex gap-3 mt-3">
            <button onClick={() => { setDraft(artifact.content || ''); setEditing(true) }}
              className="text-sm text-blue-600 hover:underline">Edit</button>
            {artifact.status !== 'done' && (
              <button onClick={markDone} className="text-sm text-green-600 hover:underline">✓ Mark Done</button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Write ArtifactsStage.tsx**

```tsx
// frontend/src/components/artifacts/ArtifactsStage.tsx
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/api/backend'
import ArtifactSelector from './ArtifactSelector'
import ArtifactCard from './ArtifactCard'
import type { Artifact, ArtifactType, ArtifactSSEEvent } from '@/types'

interface Props { callId: string; onDone: () => void }

export default function ArtifactsStage({ callId, onDone }: Props) {
  const [types, setTypes] = useState<ArtifactType[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [configs, setConfigs] = useState<{ artifact_type_id: string; mode: 'claude' | 'manual' | 'excluded' }[]>([])
  const [phase, setPhase] = useState<'select' | 'generating' | 'review'>('select')

  useEffect(() => {
    api.artifactTypes.list().then(ts => {
      setTypes(ts)
      setConfigs(ts.map(t => ({ artifact_type_id: t.id, mode: 'claude' as const })))
    })
    api.artifacts.list(callId).then(as => {
      if (as.length > 0) { setArtifacts(as); setPhase('review') }
    })
  }, [callId])

  async function handleGenerate() {
    const active = configs.filter(c => c.mode !== 'excluded')
    if (active.length === 0) return
    await api.artifacts.generate(callId, active)
    const created = await api.artifacts.list(callId)
    setArtifacts(created)
    setPhase('generating')

    const es = new EventSource(api.artifacts.streamUrl(callId))
    es.onmessage = (e) => {
      const event: ArtifactSSEEvent = JSON.parse(e.data)
      if (event.type === 'done') { es.close(); setPhase('review'); return }
      if (event.artifact_id) {
        setArtifacts(prev => prev.map(a =>
          a.id === event.artifact_id
            ? { ...a, status: event.status!, content: event.content ?? a.content, error_message: event.error_message }
            : a
        ))
      }
    }
    es.onerror = () => { es.close(); setPhase('review') }
  }

  const allDone = artifacts.length > 0 && artifacts.every(a => a.status === 'done')

  if (phase === 'select') return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Select Artifacts</h2>
      <p className="text-sm text-gray-500 mb-4">Choose how each artifact should be generated. You control which ones use Claude.</p>
      <ArtifactSelector types={types} configs={configs} onChange={setConfigs} />
      <button onClick={handleGenerate}
        disabled={configs.every(c => c.mode === 'excluded')}
        className="mt-6 bg-blue-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-40">
        Generate →
      </button>
    </div>
  )

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold">
          {phase === 'generating' ? '⏳ Generating artifacts...' : 'Review Artifacts'}
        </h2>
        {phase === 'generating' && (
          <span className="text-sm text-blue-600">
            {artifacts.filter(a => a.status === 'done').length}/{artifacts.length} done
          </span>
        )}
      </div>

      <div className="space-y-4">
        {artifacts.map(a => (
          <ArtifactCard key={a.id} artifact={a} type={types.find(t => t.id === a.artifact_type_id)}
            onUpdate={updated => setArtifacts(prev => prev.map(x => x.id === updated.id ? updated : x))} />
        ))}
      </div>

      {allDone && (
        <button onClick={onDone}
          className="mt-6 bg-green-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-green-700">
          All Done → Proceed to Topics
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire into call detail page**

Replace the `artifacts` placeholder in `page.tsx`:
```tsx
import ArtifactsStage from '@/components/artifacts/ArtifactsStage'

// In the JSX:
{call.kanban_stage === 'artifacts' && (
  <ArtifactsStage callId={callId} onDone={async () => {
    await api.calls.advanceStage(callId, 'topics')
    reload()
  }} />
)}
```

- [ ] **Step 5: Test in browser**

1. Upload a transcript → card moves to Artifacts
2. See 6 artifact types with Claude/Manual/Skip buttons
3. Set a couple to Manual, rest to Claude → click Generate
4. Watch each artifact appear live with progress indicator
5. Edit a manual one, paste content → Save
6. Mark all done → "Proceed to Topics" button appears
7. Click → card moves to Topics column on kanban

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-5] feat: artifacts stage UI — selector, SSE generation, editor"
```

---

## Slice 6: Topics Stage

**What you see at the end:** At the Topics stage, choose "Extract via Claude" or "Manual". Claude mode shows extracted topics for review/edit. Manual shows an empty list to fill in. Confirm → call moves to Done.

---

### Task 6.1: Topics API

**Files:**
- Create: `backend/api/routes/topics.py`
- Create: `backend/tests/test_topics.py`
- Modify: `backend/api/models.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add topic models to models.py**

```python
# Add to backend/api/models.py
class TopicCreate(BaseModel):
    title: str
    status: str = "active"
    summary: Optional[str] = None
    follow_up_items: list[str] = []

class TopicUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None

class TopicUpdateRecord(BaseModel):
    topic_id: str
    summary: Optional[str] = None
    follow_up_items: list[str] = []

class CallTopicsValidate(BaseModel):
    topic_updates: list[TopicUpdateRecord]

class TopicResponse(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    first_call_id: Optional[str]
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_topics.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

PID = "pid-111"
TID = "topic-555"
MOCK_TOPIC = {
    "id": TID, "project_id": PID, "title": "Budget Approval",
    "status": "active", "first_call_id": None,
    "created_at": "2026-04-09T10:00:00+00:00", "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_list_topics():
    with patch("backend.api.routes.topics.get_client") as m:
        m.return_value.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [MOCK_TOPIC]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/projects/{PID}/topics")
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Budget Approval"

@pytest.mark.asyncio
async def test_create_topic():
    with patch("backend.api.routes.topics.get_client") as m:
        m.return_value.table.return_value.insert.return_value.execute.return_value.data = [MOCK_TOPIC]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(f"/api/projects/{PID}/topics", json={"title": "Budget Approval"})
    assert r.status_code == 201
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_topics.py -v
```

- [ ] **Step 4: Write backend/api/routes/topics.py**

```python
# backend/api/routes/topics.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import TopicCreate, TopicUpdate, CallTopicsValidate, TopicResponse
from backend.database.connection import get_client
from backend.services.claude_service import extract_topics

router = APIRouter(tags=["topics"])
logger = logging.getLogger("call_tracker.topics")

@router.get("/api/projects/{project_id}/topics", response_model=list[TopicResponse])
async def list_topics(project_id: str):
    return get_client().table("topics").select("*").eq("project_id", project_id).order("created_at").execute().data

@router.post("/api/projects/{project_id}/topics", response_model=TopicResponse, status_code=201)
async def create_topic(project_id: str, payload: TopicCreate):
    db = get_client()
    result = db.table("topics").insert({"project_id": project_id, "title": payload.title, "status": payload.status}).execute()
    topic_id = result.data[0]["id"]
    if payload.summary or payload.follow_up_items:
        db.table("topic_updates").insert({"topic_id": topic_id, "summary": payload.summary, "follow_up_items": payload.follow_up_items}).execute()
    return result.data[0]

@router.patch("/api/topics/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: str, payload: TopicUpdate):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = get_client().table("topics").update(updates).eq("id", topic_id).execute()
    if not result.data:
        raise HTTPException(404, "Not found")
    return result.data[0]

@router.delete("/api/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: str):
    get_client().table("topics").delete().eq("id", topic_id).execute()

@router.post("/api/calls/{call_id}/topics/extract")
async def extract_call_topics(call_id: str):
    logger.info(f"📥 topics/extract for call {call_id}")
    db = get_client()
    call = db.table("calls").select("transcript_text, project_id").eq("id", call_id).execute()
    if not call.data:
        raise HTTPException(404, "Call not found")
    transcript = call.data[0]["transcript_text"] or ""
    project_id = call.data[0]["project_id"]
    existing = db.table("topics").select("*").eq("project_id", project_id).execute().data
    call_count = len(db.table("calls").select("id").eq("project_id", project_id).execute().data)
    topics = await extract_topics(transcript, existing, call_count)
    logger.info(f"✅ Extracted {len(topics)} topics")
    return {"topics": topics}

@router.post("/api/calls/{call_id}/topics/validate", status_code=204)
async def validate_topics(call_id: str, payload: CallTopicsValidate):
    logger.info(f"📥 topics/validate for call {call_id} — {len(payload.topic_updates)} updates")
    db = get_client()
    for u in payload.topic_updates:
        db.table("topic_updates").insert({"topic_id": u.topic_id, "call_id": call_id, "summary": u.summary, "follow_up_items": u.follow_up_items}).execute()
    db.table("calls").update({"kanban_stage": "done"}).eq("id", call_id).execute()
    logger.info(f"✅ Call {call_id} → done")
```

- [ ] **Step 5: Register router + run tests**

Add to `main.py`: `from backend.api.routes import topics` + `app.include_router(topics.router)`

```bash
cd backend && pytest tests/test_topics.py -v
```
Expected: 2 tests `PASSED`

- [ ] **Step 6: Run full test suite**

```bash
cd backend && pytest -v
```
Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-6] feat: topics API — extract, CRUD, validate"
```

---

### Task 6.2: Topics stage UI

**Files:**
- Create: `frontend/src/components/topics/TopicsStage.tsx`
- Modify: `frontend/app/projects/[id]/calls/[callId]/page.tsx`

- [ ] **Step 1: Write TopicsStage.tsx**

```tsx
// frontend/src/components/topics/TopicsStage.tsx
'use client'
import { useState } from 'react'
import { api } from '@/api/backend'

interface ExtractedTopic {
  title: string; summary: string; follow_up_items: string[]; is_new?: boolean
}

interface Props { callId: string; projectId: string; onDone: () => void }

export default function TopicsStage({ callId, projectId, onDone }: Props) {
  const [phase, setPhase] = useState<'choose' | 'extracting' | 'review' | 'manual'>('choose')
  const [topics, setTopics] = useState<ExtractedTopic[]>([])
  const [error, setError] = useState('')

  async function handleExtract() {
    setPhase('extracting')
    setError('')
    try {
      const res = await api.topics.extract(callId)
      setTopics(res.topics)
      setPhase('review')
    } catch (e: any) {
      setError(e.message)
      setPhase('choose')
    }
  }

  async function handleValidate(topicsToSave: ExtractedTopic[]) {
    const existing = await api.topics.list(projectId)
    const updates = []
    for (const t of topicsToSave.filter(t => t.title.trim())) {
      const match = existing.find(e => e.title.toLowerCase() === t.title.toLowerCase())
      let topicId: string
      if (match) {
        topicId = match.id
      } else {
        const created = await api.topics.create(projectId, { title: t.title })
        topicId = created.id
      }
      updates.push({ topic_id: topicId, summary: t.summary, follow_up_items: t.follow_up_items })
    }
    await api.topics.validate(callId, updates)
    onDone()
  }

  if (phase === 'choose') return (
    <div className="mt-4">
      <h2 className="text-lg font-semibold mb-2">Topics</h2>
      <p className="text-sm text-gray-500 mb-6">Choose how to process topics for this call</p>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}
      <div className="grid grid-cols-2 gap-4">
        <button onClick={handleExtract}
          className="p-5 border-2 rounded-xl text-left hover:border-blue-400 hover:bg-blue-50 transition-all">
          <div className="text-2xl mb-2">🤖</div>
          <div className="font-semibold text-sm mb-1">Extract via Claude</div>
          <div className="text-xs text-gray-500">AI analyzes transcript and surfaces key topics</div>
        </button>
        <button onClick={() => { setTopics([{ title: '', summary: '', follow_up_items: [] }]); setPhase('manual') }}
          className="p-5 border-2 rounded-xl text-left hover:border-blue-400 hover:bg-blue-50 transition-all">
          <div className="text-2xl mb-2">✏️</div>
          <div className="font-semibold text-sm mb-1">Manual</div>
          <div className="text-xs text-gray-500">Add topics yourself, no API call</div>
        </button>
      </div>
    </div>
  )

  if (phase === 'extracting') return (
    <div className="text-center py-20 text-blue-600">
      <div className="text-3xl mb-3 animate-pulse">🤖</div>
      <p className="font-medium">Extracting topics...</p>
    </div>
  )

  if (phase === 'review') return (
    <div className="mt-4">
      <h2 className="text-lg font-semibold mb-4">Review Topics ({topics.length})</h2>
      <div className="space-y-3">
        {topics.map((t, i) => (
          <div key={i} className="p-4 bg-white border rounded-xl">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium text-sm">{t.title}</span>
              {t.is_new && <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full">New</span>}
            </div>
            <p className="text-sm text-gray-600 mb-2">{t.summary}</p>
            {t.follow_up_items.length > 0 && (
              <ul className="space-y-0.5">{t.follow_up_items.map((f, j) => <li key={j} className="text-xs text-gray-500">• {f}</li>)}</ul>
            )}
          </div>
        ))}
      </div>
      <button onClick={() => handleValidate(topics)}
        className="mt-6 bg-green-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-green-700">
        Confirm & Complete Call ✓
      </button>
    </div>
  )

  // Manual mode
  return (
    <div className="mt-4">
      <h2 className="text-lg font-semibold mb-4">Add Topics</h2>
      <div className="space-y-3">
        {topics.map((t, i) => (
          <div key={i} className="p-4 bg-white border rounded-xl">
            <input value={t.title} onChange={e => setTopics(ts => ts.map((x, j) => j === i ? { ...x, title: e.target.value } : x))}
              placeholder="Topic title" className="w-full border rounded-lg px-3 py-2 text-sm mb-2" />
            <textarea value={t.summary} onChange={e => setTopics(ts => ts.map((x, j) => j === i ? { ...x, summary: e.target.value } : x))}
              placeholder="Summary (optional)" rows={2} className="w-full border rounded-lg px-3 py-2 text-sm resize-none mb-1" />
            <button onClick={() => setTopics(ts => ts.filter((_, j) => j !== i))} className="text-xs text-red-500 hover:underline">Remove</button>
          </div>
        ))}
      </div>
      <button onClick={() => setTopics(ts => [...ts, { title: '', summary: '', follow_up_items: [] }])}
        className="mt-2 text-sm text-blue-600 hover:underline">+ Add topic</button>
      <button onClick={() => handleValidate(topics)}
        className="mt-4 ml-4 bg-green-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-green-700">
        Confirm & Complete Call ✓
      </button>
    </div>
  )
}
```

- [ ] **Step 2: Wire into call detail page**

Replace the topics placeholder:
```tsx
import TopicsStage from '@/components/topics/TopicsStage'

{call.kanban_stage === 'topics' && (
  <TopicsStage callId={callId} projectId={projectId} onDone={reload} />
)}
```

- [ ] **Step 3: Test in browser**

1. After artifacts are done → click "Proceed to Topics"
2. Choose Claude → watch extraction → review topics → Confirm
3. Call card moves to "Done" column ✓
4. Try again with Manual → add topics manually → Confirm

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-6] feat: topics stage UI — Claude/manual, validation"
```

---

## Slice 7: Topic Dashboard

**What you see at the end:** Click "Topic Dashboard" tab in a project → see all topics across all calls, each with status badge. Add, edit, remove topics. Change status (Active / Decision Made / On Hold / Closed).

---

### Task 7.1: Topic Dashboard UI

**Files:**
- Create: `frontend/src/components/topics/TopicDashboard.tsx`
- Modify: `frontend/app/projects/[id]/page.tsx`

- [ ] **Step 1: Write TopicDashboard.tsx**

```tsx
// frontend/src/components/topics/TopicDashboard.tsx
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/api/backend'
import type { Topic, TopicStatus } from '@/types'

const STATUS: Record<TopicStatus, { label: string; style: string }> = {
  active:        { label: 'Active',        style: 'bg-blue-100 text-blue-700' },
  decision_made: { label: 'Decision Made', style: 'bg-green-100 text-green-700' },
  on_hold:       { label: 'On Hold',       style: 'bg-yellow-100 text-yellow-700' },
  closed:        { label: 'Closed',        style: 'bg-gray-100 text-gray-500' },
}

export default function TopicDashboard({ projectId }: { projectId: string }) {
  const [topics, setTopics] = useState<Topic[]>([])
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  useEffect(() => {
    api.topics.list(projectId).then(setTopics).finally(() => setLoading(false))
  }, [projectId])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!newTitle.trim()) return
    const t = await api.topics.create(projectId, { title: newTitle.trim() })
    setTopics(prev => [...prev, t])
    setNewTitle('')
    setAdding(false)
  }

  async function handleStatus(id: string, status: TopicStatus) {
    const updated = await api.topics.update(id, { status })
    setTopics(prev => prev.map(t => t.id === id ? updated : t))
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this topic?')) return
    await api.topics.delete(id)
    setTopics(prev => prev.filter(t => t.id !== id))
  }

  if (loading) return <div className="text-gray-400 py-10 text-center">Loading topics...</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="font-semibold text-lg">Topic Dashboard</h2>
          <p className="text-sm text-gray-500">{topics.length} topic{topics.length !== 1 ? 's' : ''} tracked</p>
        </div>
        <button onClick={() => setAdding(true)} className="text-sm bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">+ Add Topic</button>
      </div>

      {adding && (
        <form onSubmit={handleAdd} className="mb-4 flex gap-2">
          <input autoFocus value={newTitle} onChange={e => setNewTitle(e.target.value)}
            placeholder="Topic title" className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm">Add</button>
          <button type="button" onClick={() => setAdding(false)} className="border px-3 py-2 rounded-lg text-sm text-gray-600">Cancel</button>
        </form>
      )}

      {topics.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <p className="text-lg mb-1">No topics yet</p>
          <p className="text-sm">Topics are added during the Topics stage of each call</p>
        </div>
      ) : (
        <div className="space-y-2">
          {topics.map(topic => (
            <div key={topic.id} className="flex items-center justify-between p-4 bg-white border rounded-xl shadow-sm">
              <span className="font-medium text-sm text-gray-900">{topic.title}</span>
              <div className="flex items-center gap-2">
                <select value={topic.status} onChange={e => handleStatus(topic.id, e.target.value as TopicStatus)}
                  className={`text-xs px-2.5 py-1 rounded-full font-medium border-0 cursor-pointer ${STATUS[topic.status].style}`}>
                  {(Object.keys(STATUS) as TopicStatus[]).map(s => (
                    <option key={s} value={s}>{STATUS[s].label}</option>
                  ))}
                </select>
                <button onClick={() => handleDelete(topic.id)} className="text-gray-300 hover:text-red-500 text-lg leading-none">×</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Wire into project page**

Replace the topics tab placeholder in `app/projects/[id]/page.tsx`:
```tsx
import TopicDashboard from '@/components/topics/TopicDashboard'

{tab === 'topics' && <TopicDashboard projectId={id} />}
```

- [ ] **Step 3: Test in browser**

1. Complete a call with topics
2. Go back to project → click "Topic Dashboard" tab
3. See all topics with status badges
4. Change a status → updates instantly
5. Add a new topic manually → appears in list
6. Delete a topic → removed

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[SLICE-7] feat: topic dashboard — list, add, delete, status"
```

---

## Final: Push + verify full flow

- [ ] **Step 1: Run full test suite**

```bash
cd backend && pytest -v
```
Expected: all tests `PASSED`

- [ ] **Step 2: End-to-end test in browser**

Walk through the full flow:
1. Create a project
2. Open it → see kanban
3. Create a call → appears in "Get Transcript"
4. Click the card → upload a `.txt` transcript → advances to "Artifacts"
5. Select artifact modes → generate → watch live progress
6. Edit/mark done → proceed to Topics
7. Extract topics or add manually → confirm → card to "Done"
8. Topic Dashboard → see all topics

- [ ] **Step 3: Push**

```bash
python3 scripts/git_ops.py push
```

---

## Self-Review

| Requirement (PRD) | Slice |
|---|---|
| Projects CRUD | Slice 2 |
| Kanban board with 4 columns | Slice 3 |
| One active call per project (sequential enforcement) | Slice 3 (API) |
| MP3 transcription via local server (Whisper + pyannote) | Slice 4 |
| .txt direct upload | Slice 4 |
| Transcription status badge + offline modal | Slice 4 |
| 6 default artifact types seeded | Slice 1 |
| Per-artifact Claude/Manual/Skip mode | Slice 5 |
| Live SSE artifact generation | Slice 5 |
| Edit/paste artifact content | Slice 5 |
| Mark artifact done | Slice 5 |
| Advance to Topics only when all artifacts done | Slice 5 |
| Topics: Claude or Manual choice | Slice 6 |
| Topic extraction with previous call context | Slice 6 (API) |
| Call → Done after topic validation | Slice 6 |
| Topic Dashboard — list, status, add, delete | Slice 7 |
| No API call without user action (NFR-08) | Enforced throughout — all calls triggered by user button |
| Claude API key server-side only | claude_service.py in backend — never in frontend |
| Prompt snapshot stored immutably | Stored in `artifacts.prompt_used` at generation time |
