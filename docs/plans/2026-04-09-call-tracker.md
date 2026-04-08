# Call Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a solo-use web app that turns client call recordings into structured AI-generated artifacts and a living topic dashboard, with a kanban pipeline per call.

**Architecture:** Next.js (Vercel) calls FastAPI (Railway) for all mutations and Claude API calls. Supabase JS client handles direct reads from Next.js. A separate local FastAPI server (localhost:8000) handles MP3 transcription via Whisper + pyannote. Artifact generation streams per-artifact progress to the browser via SSE.

**Tech Stack:** Python 3.11 / FastAPI / Supabase (PostgreSQL) / Anthropic SDK (`claude-sonnet-4-6`) / Next.js 14 App Router / TypeScript / TailwindCSS / openai-whisper / pyannote.audio

**Reference docs:**
- `docs/project/config/prd.md` — locked requirements
- `docs/project/config/architecture.md` — locked architecture
- `/Users/louisgarnier/Claude/PM/transcribe_watcher.py` — transcription logic to replicate 100%

---

## Epic 1: Foundation — Database + Backend Skeleton

### Task 1.1: Project folder structure

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/main.py`
- Create: `backend/api/models.py`
- Create: `backend/api/routes/__init__.py`
- Create: `backend/services/__init__.py`
- Create: `backend/services/claude_service.py` (empty)
- Create: `backend/database/__init__.py`
- Create: `backend/database/connection.py`
- Create: `backend/database/schema.sql`
- Create: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`
- Create: `transcription/server.py` (empty)
- Create: `transcription/transcribe.py` (empty)
- Create: `transcription/requirements.txt`
- Create: `transcription/run_transcription.sh`
- Create: `transcription/setup.sh`
- Create: `.env.example`

- [ ] **Step 1: Create backend/requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.1
supabase==2.4.6
anthropic==0.26.0
python-multipart==0.0.9
httpx==0.27.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

- [ ] **Step 2: Create transcription/requirements.txt**

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

- [ ] **Step 3: Create .env.example**

```bash
# Railway backend
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
FRONTEND_URL=https://your-app.vercel.app,https://your-app-*.vercel.app
LOG_LEVEL=INFO

# Vercel frontend
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_BACKEND_URL=https://your-api.up.railway.app
NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL=http://localhost:8000

# Local transcription
HUGGINGFACE_TOKEN=hf_...
TRANSCRIPTION_PORT=8000
```

- [ ] **Step 4: Create transcription/run_transcription.sh**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || source venv/bin/activate
echo "🚀 Starting local transcription server on port ${TRANSCRIPTION_PORT:-8000}..."
uvicorn server:app --host 0.0.0.0 --port "${TRANSCRIPTION_PORT:-8000}" --reload
```

```bash
chmod +x transcription/run_transcription.sh
```

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-1] chore: scaffold project structure and requirements"
```

---

### Task 1.2: Supabase schema

**Files:**
- Create: `backend/database/schema.sql`

- [ ] **Step 1: Write schema.sql**

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Projects
CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  description TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Calls
CREATE TABLE calls (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title           TEXT NOT NULL,
  mp3_filename    TEXT,
  transcript_text TEXT,
  kanban_stage    TEXT NOT NULL DEFAULT 'transcript'
                  CHECK (kanban_stage IN ('transcript','artifacts','topics','done')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Artifact types (project_id NULL = global default)
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

-- Artifacts
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

-- Topics
CREATE TABLE topics (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','decision_made','on_hold','closed')),
  first_call_id UUID REFERENCES calls(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Topic updates (one per call per topic)
CREATE TABLE topic_updates (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id        UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  call_id         UUID REFERENCES calls(id) ON DELETE SET NULL,
  summary         TEXT,
  follow_up_items TEXT[] NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Run schema in Supabase SQL editor**

Open Supabase dashboard → SQL Editor → paste and run `schema.sql`.
Verify all 5 tables appear in Table Editor.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-1] feat: add Supabase schema (5 tables)"
```

---

### Task 1.3: Seed default artifact types

**Files:**
- Create: `backend/database/seed.sql`

- [ ] **Step 1: Write seed.sql**

```sql
INSERT INTO artifact_types (name, prompt, is_default, sort_order) VALUES
(
  'Executive Summary',
  'You are analyzing a client call transcript. Write a structured executive summary that includes: (1) Key points from the meeting — decisions made, next steps agreed, challenges raised, accountability gaps, and goals discussed. (2) Main topics in bullet points with important context. (3) Any processes or flows discussed, organized as a logical sequence of events. Be concise and factual. Use the transcript below:\n\n{{transcript}}',
  true, 1
),
(
  'Next Steps & Action Items',
  'From the following client call transcript, extract a clear list of concrete next steps and action items. Organize them in two sections: (1) Short-term — items to address before or on the next call. (2) Long-term goals — broader objectives to track over time. For each item, note who is responsible if mentioned. Transcript:\n\n{{transcript}}',
  true, 2
),
(
  'Questions for Stakeholders',
  'Based on the next steps and discussion in the following client call transcript, develop a precise list of questions to address on the next call. For each next step or open item, write 1-3 targeted questions that will drive progress. Group questions by topic. Transcript:\n\n{{transcript}}',
  true, 3
),
(
  'Email Summary (1-pager)',
  'Write a concise 1-page email summary of the following client call, suitable to send to all participants. Include: date/context, key decisions made, agreed next steps, and any open questions. Professional tone. No internal commentary. Transcript:\n\n{{transcript}}',
  true, 4
),
(
  'Email Follow-up (pre-next-call)',
  'Write a follow-up email to send before the next call, based on the following transcript. The email should: remind participants of agreed next steps, highlight any items that need preparation before the next call, and confirm the agenda for the next session. Concise, action-oriented. Transcript:\n\n{{transcript}}',
  true, 5
),
(
  'Next Call Meeting Invite Topics',
  'Based on the following call transcript, generate a structured agenda for the next meeting. List the main topics to cover, ordered by priority. For each topic, include a 1-sentence description of what needs to be discussed or decided. Transcript:\n\n{{transcript}}',
  true, 6
);
```

- [ ] **Step 2: Run seed in Supabase SQL editor**

Paste and run `seed.sql` in Supabase SQL Editor.
Verify 6 rows in `artifact_types` table with `is_default = true`.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-1] feat: seed 6 default artifact types"
```

---

### Task 1.4: FastAPI app + Supabase connection + health endpoint

**Files:**
- Create: `backend/database/connection.py`
- Create: `backend/api/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && pytest tests/test_health.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write database/connection.py**

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
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client
```

- [ ] **Step 4: Write api/main.py**

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

# CORS — must be registered LAST (outermost layer)
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

- [ ] **Step 5: Run test — expect PASS**

```bash
cd backend && pytest tests/test_health.py -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-1] feat: FastAPI app with health endpoint and Supabase connection"
```

---

### Task 1.5: Projects CRUD

**Files:**
- Create: `backend/api/routes/projects.py`
- Create: `backend/api/models.py` (initial)
- Create: `backend/tests/test_projects.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_projects.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

MOCK_PROJECT = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Test Project",
    "description": "A test project",
    "created_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_list_projects():
    with patch("backend.api.routes.projects.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.execute.return_value.data = [MOCK_PROJECT]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/projects")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Test Project"

@pytest.mark.asyncio
async def test_create_project():
    with patch("backend.api.routes.projects.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [MOCK_PROJECT]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/projects", json={"name": "Test Project", "description": "A test project"})
    assert response.status_code == 201
    assert response.json()["name"] == "Test Project"

@pytest.mark.asyncio
async def test_delete_project():
    with patch("backend.api.routes.projects.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = [MOCK_PROJECT]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete("/api/projects/11111111-1111-1111-1111-111111111111")
    assert response.status_code == 204
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_projects.py -v
```
Expected: `404` or `ImportError`

- [ ] **Step 3: Write models.py (project models)**

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

- [ ] **Step 4: Write routes/projects.py**

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
    logger.info(f"✅ Returned {len(result.data)} projects")
    return result.data

@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(payload: ProjectCreate):
    logger.info(f"📥 POST /api/projects — name={payload.name}")
    db = get_client()
    result = db.table("projects").insert(payload.model_dump()).execute()
    logger.info(f"✅ Created project {result.data[0]['id']}")
    return result.data[0]

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    logger.info(f"📥 GET /api/projects/{project_id}")
    db = get_client()
    result = db.table("projects").select("*").eq("id", project_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data[0]

@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    logger.info(f"📥 DELETE /api/projects/{project_id}")
    db = get_client()
    db.table("projects").delete().eq("id", project_id).execute()
    logger.info(f"✅ Deleted project {project_id}")
```

- [ ] **Step 5: Register router in main.py**

Add to `backend/api/main.py` after the health endpoint:
```python
from backend.api.routes import projects
app.include_router(projects.router)
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_projects.py -v
```
Expected: 3 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-1] feat: projects CRUD endpoints"
```

---

## Epic 2: Call Pipeline — Calls + Artifact Types + Artifacts Backend

### Task 2.1: Calls CRUD + stage advancement + sequential enforcement

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
    transcript_text: Optional[str] = None
    mp3_filename: Optional[str] = None

class CallStageUpdate(BaseModel):
    stage: KanbanStage

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

PROJECT_ID = "22222222-2222-2222-2222-222222222222"
CALL_ID = "33333333-3333-3333-3333-333333333333"

MOCK_CALL = {
    "id": CALL_ID,
    "project_id": PROJECT_ID,
    "title": "2026-04-09",
    "mp3_filename": None,
    "transcript_text": "Hello world transcript",
    "kanban_stage": "transcript",
    "created_at": "2026-04-09T10:00:00+00:00",
    "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_create_call_when_no_active_call():
    with patch("backend.api.routes.calls.get_client") as mock_get:
        mock_client = MagicMock()
        # No active call exists
        mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [MOCK_CALL]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/projects/{PROJECT_ID}/calls",
                json={"title": "2026-04-09", "transcript_text": "Hello world transcript"}
            )
    assert response.status_code == 201

@pytest.mark.asyncio
async def test_create_call_blocked_when_active_call_exists():
    with patch("backend.api.routes.calls.get_client") as mock_get:
        mock_client = MagicMock()
        # Active call exists
        mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = [MOCK_CALL]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/projects/{PROJECT_ID}/calls",
                json={"title": "2026-04-09"}
            )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_advance_call_stage():
    with patch("backend.api.routes.calls.get_client") as mock_get:
        mock_client = MagicMock()
        updated = {**MOCK_CALL, "kanban_stage": "artifacts"}
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(f"/api/calls/{CALL_ID}/stage", json={"stage": "artifacts"})
    assert response.status_code == 200
    assert response.json()["kanban_stage"] == "artifacts"
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_calls.py -v
```

- [ ] **Step 4: Write routes/calls.py**

```python
# backend/api/routes/calls.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import CallCreate, CallStageUpdate, CallResponse
from backend.database.connection import get_client

router = APIRouter(tags=["calls"])
logger = logging.getLogger("call_tracker.calls")

@router.get("/api/projects/{project_id}/calls", response_model=list[CallResponse])
async def list_calls(project_id: str):
    logger.info(f"📥 GET /api/projects/{project_id}/calls")
    db = get_client()
    result = db.table("calls").select("*").eq("project_id", project_id).order("created_at").execute()
    return result.data

@router.post("/api/projects/{project_id}/calls", response_model=CallResponse, status_code=201)
async def create_call(project_id: str, payload: CallCreate):
    logger.info(f"📥 POST /api/projects/{project_id}/calls — title={payload.title}")
    db = get_client()
    # Enforce sequential: reject if active call exists
    active = db.table("calls").select("id").eq("project_id", project_id).neq("kanban_stage", "done").execute()
    if active.data:
        logger.warning(f"⚠️ Blocked call creation — active call exists in project {project_id}")
        raise HTTPException(status_code=409, detail="Complete the current call before creating a new one")
    data = {**payload.model_dump(), "project_id": project_id}
    result = db.table("calls").insert(data).execute()
    logger.info(f"✅ Created call {result.data[0]['id']}")
    return result.data[0]

@router.get("/api/calls/{call_id}", response_model=CallResponse)
async def get_call(call_id: str):
    db = get_client()
    result = db.table("calls").select("*").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    return result.data[0]

@router.patch("/api/calls/{call_id}/stage", response_model=CallResponse)
async def update_call_stage(call_id: str, payload: CallStageUpdate):
    logger.info(f"📥 PATCH /api/calls/{call_id}/stage — stage={payload.stage}")
    db = get_client()
    result = db.table("calls").update({"kanban_stage": payload.stage}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    logger.info(f"✅ Call {call_id} moved to {payload.stage}")
    return result.data[0]
```

- [ ] **Step 5: Register router in main.py**

```python
from backend.api.routes import calls
app.include_router(calls.router)
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_calls.py -v
```
Expected: 3 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-2] feat: calls CRUD with sequential enforcement"
```

---

### Task 2.2: Artifact types CRUD

**Files:**
- Create: `backend/api/routes/artifact_types.py`
- Create: `backend/tests/test_artifact_types.py`
- Modify: `backend/api/models.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add artifact type models to models.py**

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
```

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_artifact_types.py
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

MOCK_TYPE = {
    "id": "44444444-4444-4444-4444-444444444444",
    "project_id": None,
    "name": "Executive Summary",
    "prompt": "Summarize the call...",
    "is_default": True,
    "sort_order": 1,
    "created_at": "2026-04-09T10:00:00+00:00",
    "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_list_artifact_types():
    with patch("backend.api.routes.artifact_types.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.execute.return_value.data = [MOCK_TYPE]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/artifact-types")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Executive Summary"
```

- [ ] **Step 3: Run test — expect FAIL**

```bash
cd backend && pytest tests/test_artifact_types.py -v
```

- [ ] **Step 4: Write routes/artifact_types.py**

```python
# backend/api/routes/artifact_types.py
import logging
from fastapi import APIRouter, HTTPException
from backend.api.models import ArtifactTypeCreate, ArtifactTypeUpdate, ArtifactTypeResponse
from backend.database.connection import get_client

router = APIRouter(prefix="/api/artifact-types", tags=["artifact-types"])
logger = logging.getLogger("call_tracker.artifact_types")

@router.get("", response_model=list[ArtifactTypeResponse])
async def list_artifact_types():
    db = get_client()
    result = db.table("artifact_types").select("*").order("sort_order").execute()
    return result.data

@router.post("", response_model=ArtifactTypeResponse, status_code=201)
async def create_artifact_type(payload: ArtifactTypeCreate):
    db = get_client()
    result = db.table("artifact_types").insert({**payload.model_dump(), "is_default": False}).execute()
    return result.data[0]

@router.patch("/{type_id}", response_model=ArtifactTypeResponse)
async def update_artifact_type(type_id: str, payload: ArtifactTypeUpdate):
    db = get_client()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = db.table("artifact_types").update(updates).eq("id", type_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    return result.data[0]

@router.delete("/{type_id}", status_code=204)
async def delete_artifact_type(type_id: str):
    db = get_client()
    db.table("artifact_types").delete().eq("id", type_id).execute()
```

- [ ] **Step 5: Register router and run test**

Add to `main.py`: `from backend.api.routes import artifact_types` and `app.include_router(artifact_types.router)`

```bash
cd backend && pytest tests/test_artifact_types.py -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-2] feat: artifact types CRUD"
```

---

### Task 2.3: Claude service + artifact generation with SSE

**Files:**
- Create: `backend/services/claude_service.py`
- Create: `backend/api/routes/artifacts.py`
- Create: `backend/tests/test_artifacts.py`
- Modify: `backend/api/models.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add artifact models to models.py**

```python
# Add to backend/api/models.py
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

- [ ] **Step 2: Write claude_service.py**

```python
# backend/services/claude_service.py
import os
import asyncio
import logging
from anthropic import AsyncAnthropic

logger = logging.getLogger("call_tracker.claude")
client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL = "claude-sonnet-4-6"

def build_prompt(prompt_template: str, transcript: str) -> str:
    """Replace {{transcript}} placeholder with actual transcript."""
    return prompt_template.replace("{{transcript}}", transcript)

async def generate_artifact(prompt_template: str, transcript: str) -> str:
    """Call Claude API with the prompt + transcript. Returns generated text."""
    prompt = build_prompt(prompt_template, transcript)
    logger.info(f"🚀 Claude API call — model={MODEL}, prompt_length={len(prompt)}")
    message = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    content = message.content[0].text
    logger.info(f"✅ Claude response received — length={len(content)}")
    return content

async def extract_topics(transcript: str, existing_topics: list[dict], call_number: int) -> list[dict]:
    """
    Extract or update topics from transcript.
    Returns list of {title, summary, follow_up_items, is_new} dicts.
    """
    if call_number == 1:
        prompt = f"""Analyze this client call transcript and extract the key recurring topics, themes, and items that need follow-up.

For each topic, provide:
- title: short name (5 words max)
- summary: what happened with this topic in this call (2-3 sentences)
- follow_up_items: list of specific follow-up actions needed

Return as JSON array: [{{"title": "...", "summary": "...", "follow_up_items": ["...", "..."]}}]

Transcript:
{transcript}"""
    else:
        existing_str = "\n".join([f"- {t['title']}: {t.get('latest_summary', '')}" for t in existing_topics])
        prompt = f"""You are reviewing a new client call transcript. Here are the existing topics being tracked for this project:

{existing_str}

For this new call:
1. Check each existing topic — did it come up? If yes, provide an updated summary and new follow-up items.
2. Identify any NEW topics not in the existing list.

Return as JSON array with ALL topics (updated + new):
[{{"title": "...", "summary": "...", "follow_up_items": ["..."], "is_new": true/false}}]

New call transcript:
{transcript}"""

    logger.info(f"🚀 Claude topic extraction — call_number={call_number}, existing_topics={len(existing_topics)}")
    message = await client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    import json, re
    text = message.content[0].text
    # Extract JSON from response
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        raise ValueError(f"Claude did not return valid JSON array: {text[:200]}")
    topics = json.loads(match.group())
    logger.info(f"✅ Extracted {len(topics)} topics")
    return topics
```

- [ ] **Step 3: Write failing test for artifact generation**

```python
# backend/tests/test_artifacts.py
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

CALL_ID = "33333333-3333-3333-3333-333333333333"
TYPE_ID = "44444444-4444-4444-4444-444444444444"
ARTIFACT_ID = "55555555-5555-5555-5555-555555555555"

MOCK_ARTIFACT = {
    "id": ARTIFACT_ID,
    "call_id": CALL_ID,
    "artifact_type_id": TYPE_ID,
    "prompt_used": "Summarize...",
    "content": None,
    "mode": "claude",
    "status": "pending",
    "error_message": None,
    "created_at": "2026-04-09T10:00:00+00:00",
    "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_update_artifact_content():
    with patch("backend.api.routes.artifacts.get_client") as mock_get:
        mock_client = MagicMock()
        updated = {**MOCK_ARTIFACT, "content": "Generated content here"}
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/artifacts/{ARTIFACT_ID}",
                json={"content": "Generated content here"}
            )
    assert response.status_code == 200
    assert response.json()["content"] == "Generated content here"

@pytest.mark.asyncio
async def test_mark_artifact_done():
    with patch("backend.api.routes.artifacts.get_client") as mock_get:
        mock_client = MagicMock()
        done = {**MOCK_ARTIFACT, "status": "done"}
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [done]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(f"/api/artifacts/{ARTIFACT_ID}/done")
    assert response.status_code == 200
    assert response.json()["status"] == "done"
```

- [ ] **Step 4: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_artifacts.py -v
```

- [ ] **Step 5: Write routes/artifacts.py**

```python
# backend/api/routes/artifacts.py
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from backend.api.models import ArtifactGenerateRequest, ArtifactUpdate, ArtifactResponse
from backend.database.connection import get_client
from backend.services.claude_service import generate_artifact
import json

router = APIRouter(tags=["artifacts"])
logger = logging.getLogger("call_tracker.artifacts")

@router.post("/api/calls/{call_id}/artifacts/generate")
async def start_artifact_generation(call_id: str, payload: ArtifactGenerateRequest):
    """Create artifact records and return SSE stream URL. Claude artifacts generate via SSE stream."""
    logger.info(f"📥 POST /api/calls/{call_id}/artifacts/generate — {len(payload.artifact_configs)} artifacts")
    db = get_client()

    # Get transcript
    call = db.table("calls").select("transcript_text").eq("id", call_id).execute()
    if not call.data or not call.data[0].get("transcript_text"):
        raise HTTPException(status_code=400, detail="Call has no transcript")
    transcript = call.data[0]["transcript_text"]

    artifact_ids = []
    for config in payload.artifact_configs:
        # Get artifact type + prompt
        atype = db.table("artifact_types").select("*").eq("id", config.artifact_type_id).execute()
        if not atype.data:
            raise HTTPException(status_code=404, detail=f"Artifact type {config.artifact_type_id} not found")
        prompt = atype.data[0]["prompt"]

        # Create artifact record
        record = {
            "call_id": call_id,
            "artifact_type_id": config.artifact_type_id,
            "prompt_used": prompt,
            "mode": config.mode,
            "status": "pending" if config.mode == "claude" else "done",
            "content": None
        }
        result = db.table("artifacts").insert(record).execute()
        artifact_ids.append(result.data[0]["id"])

    logger.info(f"✅ Created {len(artifact_ids)} artifact records")
    return {"artifact_ids": artifact_ids}

@router.get("/api/calls/{call_id}/artifacts/stream")
async def stream_artifact_generation(call_id: str):
    """SSE endpoint — generates all pending Claude artifacts and streams status updates."""
    db = get_client()

    call = db.table("calls").select("transcript_text").eq("id", call_id).execute()
    if not call.data:
        raise HTTPException(status_code=404, detail="Call not found")
    transcript = call.data[0]["transcript_text"] or ""

    pending = db.table("artifacts").select("*, artifact_types(name, prompt)").eq("call_id", call_id).eq("mode", "claude").eq("status", "pending").execute()

    async def generate():
        tasks = []
        for artifact in pending.data:
            tasks.append(_generate_one(artifact, transcript, db))

        for coro in asyncio.as_completed(tasks):
            event = await coro
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

async def _generate_one(artifact: dict, transcript: str, db) -> dict:
    artifact_id = artifact["id"]
    prompt = artifact["artifact_types"]["prompt"]
    db.table("artifacts").update({"status": "generating"}).eq("id", artifact_id).execute()
    try:
        content = await generate_artifact(prompt, transcript)
        db.table("artifacts").update({"status": "done", "content": content}).eq("id", artifact_id).execute()
        return {"type": "update", "artifact_id": artifact_id, "status": "done", "content": content}
    except Exception as e:
        logger.error(f"❌ Artifact {artifact_id} failed: {e}")
        db.table("artifacts").update({"status": "error", "error_message": str(e)}).eq("id", artifact_id).execute()
        return {"type": "update", "artifact_id": artifact_id, "status": "error", "error_message": str(e)}

@router.get("/api/calls/{call_id}/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(call_id: str):
    db = get_client()
    result = db.table("artifacts").select("*").eq("call_id", call_id).execute()
    return result.data

@router.patch("/api/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(artifact_id: str, payload: ArtifactUpdate):
    db = get_client()
    result = db.table("artifacts").update({"content": payload.content}).eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result.data[0]

@router.patch("/api/artifacts/{artifact_id}/done", response_model=ArtifactResponse)
async def mark_artifact_done(artifact_id: str):
    db = get_client()
    result = db.table("artifacts").update({"status": "done"}).eq("id", artifact_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result.data[0]
```

- [ ] **Step 6: Register router and run tests**

Add to `main.py`: `from backend.api.routes import artifacts` and `app.include_router(artifacts.router)`

```bash
cd backend && pytest tests/test_artifacts.py -v
```
Expected: 2 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-2] feat: artifact generation with SSE + Claude service"
```

---

### Task 2.4: Topics backend (extraction + CRUD + validation)

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

class TopicUpdateCreate(BaseModel):
    topic_id: str
    summary: Optional[str] = None
    follow_up_items: list[str] = []

class CallTopicsValidate(BaseModel):
    topic_updates: list[TopicUpdateCreate]

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
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from backend.api.main import app

PROJECT_ID = "22222222-2222-2222-2222-222222222222"
CALL_ID = "33333333-3333-3333-3333-333333333333"
TOPIC_ID = "66666666-6666-6666-6666-666666666666"

MOCK_TOPIC = {
    "id": TOPIC_ID,
    "project_id": PROJECT_ID,
    "title": "Budget Approval",
    "status": "active",
    "first_call_id": CALL_ID,
    "created_at": "2026-04-09T10:00:00+00:00",
    "updated_at": "2026-04-09T10:00:00+00:00"
}

@pytest.mark.asyncio
async def test_list_topics():
    with patch("backend.api.routes.topics.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [MOCK_TOPIC]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/projects/{PROJECT_ID}/topics")
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Budget Approval"

@pytest.mark.asyncio
async def test_manually_add_topic():
    with patch("backend.api.routes.topics.get_client") as mock_get:
        mock_client = MagicMock()
        mock_client.table.return_value.insert.return_value.execute.return_value.data = [MOCK_TOPIC]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/projects/{PROJECT_ID}/topics",
                json={"title": "Budget Approval"}
            )
    assert response.status_code == 201
```

- [ ] **Step 3: Run tests — expect FAIL**

```bash
cd backend && pytest tests/test_topics.py -v
```

- [ ] **Step 4: Write routes/topics.py**

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
    db = get_client()
    result = db.table("topics").select("*").eq("project_id", project_id).order("created_at").execute()
    return result.data

@router.post("/api/projects/{project_id}/topics", response_model=TopicResponse, status_code=201)
async def create_topic(project_id: str, payload: TopicCreate):
    logger.info(f"📥 POST /api/projects/{project_id}/topics — title={payload.title}")
    db = get_client()
    record = {"project_id": project_id, "title": payload.title, "status": payload.status}
    result = db.table("topics").insert(record).execute()
    topic_id = result.data[0]["id"]
    # Create initial topic_update if summary provided
    if payload.summary or payload.follow_up_items:
        db.table("topic_updates").insert({
            "topic_id": topic_id,
            "summary": payload.summary,
            "follow_up_items": payload.follow_up_items
        }).execute()
    logger.info(f"✅ Created topic {topic_id}")
    return result.data[0]

@router.patch("/api/topics/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: str, payload: TopicUpdate):
    db = get_client()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = db.table("topics").update(updates).eq("id", topic_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Topic not found")
    return result.data[0]

@router.delete("/api/topics/{topic_id}", status_code=204)
async def delete_topic(topic_id: str):
    db = get_client()
    db.table("topics").delete().eq("id", topic_id).execute()

@router.post("/api/calls/{call_id}/topics/extract")
async def extract_call_topics(call_id: str):
    """Claude extracts/updates topics from call transcript."""
    logger.info(f"📥 POST /api/calls/{call_id}/topics/extract")
    db = get_client()

    call = db.table("calls").select("transcript_text, project_id").eq("id", call_id).execute()
    if not call.data:
        raise HTTPException(status_code=404, detail="Call not found")
    transcript = call.data[0]["transcript_text"] or ""
    project_id = call.data[0]["project_id"]

    existing = db.table("topics").select("*").eq("project_id", project_id).execute()
    call_number = len(db.table("calls").select("id").eq("project_id", project_id).execute().data)

    topics = await extract_topics(transcript, existing.data, call_number)
    logger.info(f"✅ Extracted {len(topics)} topics for call {call_id}")
    return {"topics": topics}

@router.post("/api/calls/{call_id}/topics/validate", status_code=204)
async def validate_call_topics(call_id: str, payload: CallTopicsValidate):
    """Save topic updates and advance call to Done."""
    logger.info(f"📥 POST /api/calls/{call_id}/topics/validate — {len(payload.topic_updates)} updates")
    db = get_client()

    for update in payload.topic_updates:
        db.table("topic_updates").insert({
            "topic_id": update.topic_id,
            "call_id": call_id,
            "summary": update.summary,
            "follow_up_items": update.follow_up_items
        }).execute()

    db.table("calls").update({"kanban_stage": "done"}).eq("id", call_id).execute()
    logger.info(f"✅ Call {call_id} validated and moved to done")
```

- [ ] **Step 5: Register router and run tests**

Add to `main.py`: `from backend.api.routes import topics` and `app.include_router(topics.router)`

```bash
cd backend && pytest tests/test_topics.py -v
```
Expected: 2 tests `PASSED`

- [ ] **Step 6: Run full backend test suite**

```bash
cd backend && pytest -v
```
Expected: all tests `PASSED`

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-2] feat: topics CRUD + Claude extraction + call validation"
```

---

## Epic 3: Local Transcription Server

### Task 3.1: Port transcribe_watcher.py as a FastAPI endpoint

**Files:**
- Create: `transcription/transcribe.py`
- Create: `transcription/server.py`
- Create: `transcription/tests/test_transcribe.py`

Reference: `/Users/louisgarnier/Claude/PM/transcribe_watcher.py` — replicate this logic 100%.

- [ ] **Step 1: Write transcription/transcribe.py (port of transcribe_watcher.py)**

```python
# transcription/transcribe.py
"""
Transcription pipeline — replicates /Users/louisgarnier/Claude/PM/transcribe_watcher.py 100%.
Whisper (medium model) + pyannote speaker diarization.
"""
import os
import tempfile
import logging
from pathlib import Path
import whisper
from pyannote.audio import Pipeline

logger = logging.getLogger("transcription")

_whisper_model = None
_diarization_pipeline = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        logger.info("🚀 Loading Whisper medium model...")
        _whisper_model = whisper.load_model("medium")
        logger.info("✅ Whisper model loaded")
    return _whisper_model

def get_diarization_pipeline():
    global _diarization_pipeline
    if _diarization_pipeline is None:
        token = os.environ.get("HUGGINGFACE_TOKEN")
        logger.info("🚀 Loading pyannote diarization pipeline...")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token
        )
        logger.info("✅ Pyannote pipeline loaded")
    return _diarization_pipeline

def merge_transcript_with_speakers(segments: list, diarization) -> list:
    """Assign speaker label to each Whisper segment based on pyannote diarization."""
    merged = []
    for segment in segments:
        start = segment["start"]
        end = segment["end"]
        text = segment["text"].strip()
        # Find dominant speaker in this segment's time window
        speaker = "SPEAKER_0"
        max_overlap = 0
        for turn, _, spk in diarization.itertracks(yield_label=True):
            overlap = min(turn.end, end) - max(turn.start, start)
            if overlap > max_overlap:
                max_overlap = overlap
                speaker = spk
        merged.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return merged

def format_transcript(merged: list, filename: str, duration: float) -> str:
    """Format transcript in the same output format as transcribe_watcher.py."""
    from datetime import timedelta
    lines = [
        f"Transcript: {Path(filename).stem}",
        f"Duration: {str(timedelta(seconds=int(duration)))}",
        ""
    ]
    for seg in merged:
        ts = str(timedelta(seconds=int(seg["start"])))[2:]  # MM:SS
        lines.append(f"[{ts}] {seg['speaker']}: {seg['text']}")
    return "\n".join(lines)

def transcribe_audio(audio_path: str, filename: str) -> dict:
    """
    Full pipeline: Whisper + pyannote + merge.
    Returns {transcript_text, duration, speakers}.
    """
    logger.info(f"📥 Transcribing {filename}...")

    model = get_whisper_model()
    pipeline = get_diarization_pipeline()

    # Whisper transcription
    logger.info("🔄 Running Whisper...")
    result = model.transcribe(audio_path, word_timestamps=False)
    segments = result["segments"]
    duration = result.get("duration", 0)

    # Speaker diarization
    logger.info("🔄 Running pyannote diarization...")
    diarization = pipeline(audio_path)

    # Merge
    merged = merge_transcript_with_speakers(segments, diarization)
    speakers = list(set(s["speaker"] for s in merged))

    transcript_text = format_transcript(merged, filename, duration)
    logger.info(f"✅ Transcription complete — {len(segments)} segments, {len(speakers)} speakers")

    return {
        "transcript_text": transcript_text,
        "duration": duration,
        "speakers": speakers
    }
```

- [ ] **Step 2: Write transcription/server.py**

```python
# transcription/server.py
import os
import tempfile
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from transcribe import transcribe_audio

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [transcription] %(levelname)s: %(message)s"
)
logger = logging.getLogger("transcription.server")

app = FastAPI(title="Call Tracker — Local Transcription Server")

# Allow calls from Vercel-hosted frontend + localhost dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local server — safe to allow all
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 files are supported")

    logger.info(f"📥 POST /transcribe — filename={file.filename}")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = transcribe_audio(tmp_path, file.filename)
        logger.info(f"✅ Transcription complete — duration={result['duration']:.1f}s")
        return result
    except Exception as e:
        logger.error(f"❌ Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 3: Write failing test**

```python
# transcription/tests/test_transcribe.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, ".")
from server import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_transcribe_rejects_non_mp3():
    import io
    response = client.post(
        "/transcribe",
        files={"file": ("test.txt", io.BytesIO(b"not audio"), "text/plain")}
    )
    assert response.status_code == 400
    assert "mp3" in response.json()["detail"].lower()

def test_transcribe_mp3_calls_pipeline():
    import io
    with patch("server.transcribe_audio") as mock_transcribe:
        mock_transcribe.return_value = {
            "transcript_text": "[00:00] SPEAKER_0: Hello",
            "duration": 10.0,
            "speakers": ["SPEAKER_0"]
        }
        response = client.post(
            "/transcribe",
            files={"file": ("call.mp3", io.BytesIO(b"fake audio"), "audio/mpeg")}
        )
    assert response.status_code == 200
    assert "transcript_text" in response.json()
    assert "SPEAKER_0" in response.json()["transcript_text"]
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd transcription && python -m pytest tests/ -v
```
Expected: 3 tests `PASSED` (transcribe_audio is mocked, no model loading)

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-3] feat: local transcription server (Whisper + pyannote)"
```

---

## Epic 4: Frontend

### Task 4.1: Next.js setup + types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/backend.ts`
- Create: `frontend/src/api/local.ts`
- Modify: `frontend/app/layout.tsx`

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

export interface TopicUpdate {
  id: string
  topic_id: string
  call_id?: string
  summary?: string
  follow_up_items: string[]
  created_at: string
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
const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8001'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

// Projects
export const api = {
  projects: {
    list: () => request<import('@/types').Project[]>('/api/projects'),
    create: (data: { name: string; description?: string }) =>
      request<import('@/types').Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  },
  calls: {
    list: (projectId: string) => request<import('@/types').Call[]>(`/api/projects/${projectId}/calls`),
    create: (projectId: string, data: { title: string; transcript_text?: string; mp3_filename?: string }) =>
      request<import('@/types').Call>(`/api/projects/${projectId}/calls`, { method: 'POST', body: JSON.stringify(data) }),
    get: (callId: string) => request<import('@/types').Call>(`/api/calls/${callId}`),
    advanceStage: (callId: string, stage: import('@/types').KanbanStage) =>
      request<import('@/types').Call>(`/api/calls/${callId}/stage`, { method: 'PATCH', body: JSON.stringify({ stage }) }),
  },
  artifactTypes: {
    list: () => request<import('@/types').ArtifactType[]>('/api/artifact-types'),
    create: (data: { name: string; prompt: string; project_id?: string }) =>
      request<import('@/types').ArtifactType>('/api/artifact-types', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { name?: string; prompt?: string }) =>
      request<import('@/types').ArtifactType>(`/api/artifact-types/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/api/artifact-types/${id}`, { method: 'DELETE' }),
  },
  artifacts: {
    list: (callId: string) => request<import('@/types').Artifact[]>(`/api/calls/${callId}/artifacts`),
    generate: (callId: string, configs: { artifact_type_id: string; mode: string }[]) =>
      request<{ artifact_ids: string[] }>(`/api/calls/${callId}/artifacts/generate`, {
        method: 'POST', body: JSON.stringify({ artifact_configs: configs })
      }),
    streamUrl: (callId: string) => `${BASE}/api/calls/${callId}/artifacts/stream`,
    update: (id: string, content: string) =>
      request<import('@/types').Artifact>(`/api/artifacts/${id}`, { method: 'PATCH', body: JSON.stringify({ content }) }),
    markDone: (id: string) =>
      request<import('@/types').Artifact>(`/api/artifacts/${id}/done`, { method: 'PATCH' }),
  },
  topics: {
    list: (projectId: string) => request<import('@/types').Topic[]>(`/api/projects/${projectId}/topics`),
    create: (projectId: string, data: { title: string; status?: string }) =>
      request<import('@/types').Topic>(`/api/projects/${projectId}/topics`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { title?: string; status?: string }) =>
      request<import('@/types').Topic>(`/api/topics/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/api/topics/${id}`, { method: 'DELETE' }),
    extract: (callId: string) =>
      request<{ topics: any[] }>(`/api/calls/${callId}/topics/extract`, { method: 'POST' }),
    validate: (callId: string, topic_updates: any[]) =>
      request<void>(`/api/calls/${callId}/topics/validate`, { method: 'POST', body: JSON.stringify({ topic_updates }) }),
  }
}
```

- [ ] **Step 3: Write frontend/src/api/local.ts**

```typescript
// frontend/src/api/local.ts
const LOCAL_URL = process.env.NEXT_PUBLIC_LOCAL_TRANSCRIPTION_URL || 'http://localhost:8000'

export async function checkTranscriptionHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${LOCAL_URL}/health`, { signal: AbortSignal.timeout(2000) })
    return res.ok
  } catch {
    return false
  }
}

export async function transcribeAudio(file: File): Promise<{ transcript_text: string; duration: number; speakers: string[] }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${LOCAL_URL}/transcribe`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Transcription failed')
  }
  return res.json()
}
```

- [ ] **Step 4: Update layout.tsx with TranscriptionStatusBadge placeholder**

```typescript
// frontend/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = { title: 'Call Tracker' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center justify-between">
          <span className="font-semibold text-gray-900">Call Tracker</span>
          <div id="transcription-status" />
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  )
}
```

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-4] feat: Next.js types, API client, layout"
```

---

### Task 4.2: Project list page

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/src/components/ui/TranscriptionStatusBadge.tsx`
- Create: `frontend/__tests__/ProjectList.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/__tests__/ProjectList.test.tsx
import { render, screen } from '@testing-library/react'
import ProjectList from '@/components/projects/ProjectList'

const mockProjects = [
  { id: '1', name: 'FactSet Q1', description: 'Earnings call', created_at: '2026-04-09T10:00:00Z' }
]

jest.mock('@/api/backend', () => ({
  api: { projects: { list: jest.fn().mockResolvedValue(mockProjects) } }
}))

test('renders project names', async () => {
  render(<ProjectList />)
  expect(await screen.findByText('FactSet Q1')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npx jest __tests__/ProjectList.test.tsx
```

- [ ] **Step 3: Create frontend/src/components/projects/ProjectList.tsx**

```typescript
// frontend/src/components/projects/ProjectList.tsx
'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api } from '@/api/backend'
import type { Project } from '@/types'

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')

  useEffect(() => {
    api.projects.list().then(setProjects).finally(() => setLoading(false))
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    const project = await api.projects.create({ name: name.trim() })
    setProjects(p => [project, ...p])
    setName('')
    setCreating(false)
  }

  if (loading) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Projects</h1>
        <button onClick={() => setCreating(true)} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
          New Project
        </button>
      </div>

      {creating && (
        <form onSubmit={handleCreate} className="mb-4 p-4 border rounded-lg bg-white">
          <input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Project name (e.g. FactSet Q1 2026)"
            className="w-full border rounded px-3 py-2 mb-3 text-sm"
          />
          <div className="flex gap-2">
            <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Create</button>
            <button type="button" onClick={() => setCreating(false)} className="border px-4 py-2 rounded text-sm">Cancel</button>
          </div>
        </form>
      )}

      {projects.length === 0 ? (
        <p className="text-gray-500 text-center py-12">No projects yet. Create your first one.</p>
      ) : (
        <div className="space-y-3">
          {projects.map(p => (
            <Link key={p.id} href={`/projects/${p.id}`} className="block p-4 bg-white border rounded-lg hover:border-blue-400 transition-colors">
              <div className="font-medium">{p.name}</div>
              {p.description && <div className="text-sm text-gray-500 mt-1">{p.description}</div>}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Update app/page.tsx**

```typescript
// frontend/app/page.tsx
import ProjectList from '@/components/projects/ProjectList'
export default function Home() { return <ProjectList /> }
```

- [ ] **Step 5: Create TranscriptionStatusBadge.tsx**

```typescript
// frontend/src/components/ui/TranscriptionStatusBadge.tsx
'use client'
import { useEffect, useState } from 'react'
import { checkTranscriptionHealth } from '@/api/local'

export default function TranscriptionStatusBadge() {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    const check = async () => setOnline(await checkTranscriptionHealth())
    check()
    const interval = setInterval(check, 30000)
    return () => clearInterval(interval)
  }, [])

  if (online === null) return null

  return (
    <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${online ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-green-500' : 'bg-amber-500'}`} />
      Transcription {online ? 'Online' : 'Offline'}
    </div>
  )
}
```

- [ ] **Step 6: Run test — expect PASS**

```bash
cd frontend && npx jest __tests__/ProjectList.test.tsx
```

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-4] feat: project list page + transcription status badge"
```

---

### Task 4.3: Project view — Kanban board

**Files:**
- Create: `frontend/app/projects/[id]/page.tsx`
- Create: `frontend/src/components/kanban/KanbanBoard.tsx`
- Create: `frontend/src/components/kanban/CallCard.tsx`
- Create: `frontend/__tests__/KanbanBoard.test.tsx`

- [ ] **Step 1: Write failing test**

```typescript
// frontend/__tests__/KanbanBoard.test.tsx
import { render, screen } from '@testing-library/react'
import KanbanBoard from '@/components/kanban/KanbanBoard'
import type { Call } from '@/types'

const mockCalls: Call[] = [
  { id: '1', project_id: 'p1', title: '2026-04-09', kanban_stage: 'artifacts', mp3_filename: undefined, transcript_text: 'text', created_at: '', updated_at: '' }
]

test('renders call card in correct column', () => {
  render(<KanbanBoard projectId="p1" calls={mockCalls} onNewCall={jest.fn()} activeCallExists={false} />)
  expect(screen.getByText('2026-04-09')).toBeInTheDocument()
  expect(screen.getByText('Artifacts')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd frontend && npx jest __tests__/KanbanBoard.test.tsx
```

- [ ] **Step 3: Create KanbanBoard.tsx**

```typescript
// frontend/src/components/kanban/KanbanBoard.tsx
import Link from 'next/link'
import type { Call, KanbanStage } from '@/types'

const STAGES: { key: KanbanStage; label: string }[] = [
  { key: 'transcript', label: 'Get Transcript' },
  { key: 'artifacts', label: 'Artifacts' },
  { key: 'topics', label: 'Topics' },
  { key: 'done', label: 'Done ✓' },
]

interface Props {
  projectId: string
  calls: Call[]
  onNewCall: () => void
  activeCallExists: boolean
}

export default function KanbanBoard({ projectId, calls, onNewCall, activeCallExists }: Props) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {STAGES.map(stage => (
        <div key={stage.key} className="flex-shrink-0 w-64">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-medium text-sm text-gray-700">{stage.label}</h3>
            <span className="text-xs text-gray-400">{calls.filter(c => c.kanban_stage === stage.key).length}</span>
          </div>
          <div className="space-y-2 min-h-32">
            {calls.filter(c => c.kanban_stage === stage.key).map(call => (
              <Link key={call.id} href={`/projects/${projectId}/calls/${call.id}`}>
                <div className="p-3 bg-white border rounded-lg shadow-sm hover:border-blue-400 cursor-pointer">
                  <div className="font-medium text-sm">{call.title}</div>
                  <div className="text-xs text-gray-500 mt-1 capitalize">{stage.label}</div>
                </div>
              </Link>
            ))}
          </div>
          {stage.key === 'transcript' && (
            <button
              onClick={onNewCall}
              disabled={activeCallExists}
              className="mt-2 w-full border-2 border-dashed rounded-lg p-2 text-sm text-gray-400 hover:border-blue-400 hover:text-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              + New Call
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd frontend && npx jest __tests__/KanbanBoard.test.tsx
```

- [ ] **Step 5: Create app/projects/[id]/page.tsx**

```typescript
// frontend/app/projects/[id]/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import KanbanBoard from '@/components/kanban/KanbanBoard'
import TopicDashboard from '@/components/topics/TopicDashboard'
import { api } from '@/api/backend'
import type { Project, Call } from '@/types'

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>()
  const [project, setProject] = useState<Project | null>(null)
  const [calls, setCalls] = useState<Call[]>([])
  const [tab, setTab] = useState<'kanban' | 'topics'>('kanban')
  const [showNewCall, setShowNewCall] = useState(false)

  useEffect(() => {
    api.projects.list().then(ps => setProject(ps.find(p => p.id === id) || null))
    api.calls.list(id).then(setCalls)
  }, [id])

  const activeCallExists = calls.some(c => c.kanban_stage !== 'done')

  async function handleCreateCall(title: string) {
    const call = await api.calls.create(id, { title })
    setCalls(c => [...c, call])
    setShowNewCall(false)
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">{project?.name}</h1>
      <div className="flex gap-4 border-b mb-6">
        {(['kanban', 'topics'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`pb-2 text-sm capitalize ${tab === t ? 'border-b-2 border-blue-600 text-blue-600 font-medium' : 'text-gray-500'}`}>
            {t === 'kanban' ? 'Kanban Board' : 'Topic Dashboard'}
          </button>
        ))}
      </div>
      {tab === 'kanban' && (
        <>
          {showNewCall && (
            <NewCallForm onSubmit={handleCreateCall} onCancel={() => setShowNewCall(false)} />
          )}
          <KanbanBoard projectId={id} calls={calls} onNewCall={() => setShowNewCall(true)} activeCallExists={activeCallExists} />
        </>
      )}
      {tab === 'topics' && <TopicDashboard projectId={id} />}
    </div>
  )
}

function NewCallForm({ onSubmit, onCancel }: { onSubmit: (title: string) => void; onCancel: () => void }) {
  const [title, setTitle] = useState('')
  return (
    <form onSubmit={e => { e.preventDefault(); if (title.trim()) onSubmit(title.trim()) }} className="mb-4 p-4 border rounded-lg bg-white max-w-sm">
      <input autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="Call title (e.g. 2026-04-09)" className="w-full border rounded px-3 py-2 mb-3 text-sm" />
      <div className="flex gap-2">
        <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Create</button>
        <button type="button" onClick={onCancel} className="border px-4 py-2 rounded text-sm">Cancel</button>
      </div>
    </form>
  )
}
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-4] feat: project page with kanban board"
```

---

### Task 4.4: Call detail — Transcript stage + Artifact stage

**Files:**
- Create: `frontend/app/projects/[id]/calls/[callId]/page.tsx`
- Create: `frontend/src/components/artifacts/ArtifactSelector.tsx`
- Create: `frontend/src/components/artifacts/ArtifactCard.tsx`

- [ ] **Step 1: Create ArtifactSelector.tsx**

```typescript
// frontend/src/components/artifacts/ArtifactSelector.tsx
'use client'
import type { ArtifactType } from '@/types'

type ArtifactMode = 'claude' | 'manual' | 'excluded'

interface ArtifactConfig {
  artifact_type_id: string
  mode: ArtifactMode
}

interface Props {
  artifactTypes: ArtifactType[]
  configs: ArtifactConfig[]
  onChange: (configs: ArtifactConfig[]) => void
}

const MODE_LABELS: Record<ArtifactMode, string> = {
  claude: '🤖 Claude',
  manual: '✏️ Manual',
  excluded: '✗ Skip'
}

export default function ArtifactSelector({ artifactTypes, configs, onChange }: Props) {
  function setMode(typeId: string, mode: ArtifactMode) {
    onChange(configs.map(c => c.artifact_type_id === typeId ? { ...c, mode } : c))
  }

  return (
    <div className="space-y-2">
      {artifactTypes.map(type => {
        const config = configs.find(c => c.artifact_type_id === type.id)
        const mode = config?.mode || 'excluded'
        return (
          <div key={type.id} className="flex items-center justify-between p-3 border rounded-lg bg-white">
            <span className="text-sm font-medium">{type.name}</span>
            <div className="flex gap-1">
              {(['claude', 'manual', 'excluded'] as ArtifactMode[]).map(m => (
                <button key={m} onClick={() => setMode(type.id, m)}
                  className={`px-2 py-1 rounded text-xs ${mode === m ? 'bg-blue-100 text-blue-700 font-medium' : 'text-gray-500 hover:bg-gray-100'}`}>
                  {MODE_LABELS[m]}
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

- [ ] **Step 2: Create ArtifactCard.tsx**

```typescript
// frontend/src/components/artifacts/ArtifactCard.tsx
'use client'
import { useState } from 'react'
import { api } from '@/api/backend'
import type { Artifact, ArtifactType } from '@/types'

interface Props {
  artifact: Artifact
  artifactType?: ArtifactType
  onUpdate: (updated: Artifact) => void
}

const STATUS_STYLES = {
  pending: 'bg-gray-100 text-gray-600',
  generating: 'bg-blue-100 text-blue-600 animate-pulse',
  done: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700'
}

export default function ArtifactCard({ artifact, artifactType, onUpdate }: Props) {
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState(artifact.content || '')

  async function handleSave() {
    const updated = await api.artifacts.update(artifact.id, content)
    onUpdate(updated)
    setEditing(false)
  }

  async function handleMarkDone() {
    const updated = await api.artifacts.markDone(artifact.id)
    onUpdate(updated)
  }

  return (
    <div className="border rounded-lg p-4 bg-white">
      <div className="flex justify-between items-start mb-3">
        <h4 className="font-medium text-sm">{artifactType?.name || 'Artifact'}</h4>
        <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLES[artifact.status]}`}>
          {artifact.status}
        </span>
      </div>

      {artifact.status === 'error' && (
        <p className="text-red-600 text-sm mb-2">Error: {artifact.error_message}</p>
      )}

      {editing ? (
        <>
          <textarea value={content} onChange={e => setContent(e.target.value)}
            className="w-full border rounded p-2 text-sm min-h-32 resize-y" />
          <div className="flex gap-2 mt-2">
            <button onClick={handleSave} className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm">Save</button>
            <button onClick={() => setEditing(false)} className="border px-3 py-1.5 rounded text-sm">Cancel</button>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm text-gray-700 whitespace-pre-wrap">{content || <span className="text-gray-400 italic">No content yet</span>}</p>
          <div className="flex gap-2 mt-3">
            <button onClick={() => setEditing(true)} className="text-sm text-blue-600 hover:underline">Edit</button>
            {artifact.status !== 'done' && (
              <button onClick={handleMarkDone} className="text-sm text-green-600 hover:underline">Mark Done</button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create call detail page**

```typescript
// frontend/app/projects/[id]/calls/[callId]/page.tsx
'use client'
import { useEffect, useState, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/api/backend'
import { transcribeAudio, checkTranscriptionHealth } from '@/api/local'
import ArtifactSelector from '@/components/artifacts/ArtifactSelector'
import ArtifactCard from '@/components/artifacts/ArtifactCard'
import TopicsStage from '@/components/topics/TopicsStage'
import type { Call, ArtifactType, Artifact, KanbanStage, ArtifactSSEEvent } from '@/types'

const STAGE_ORDER: KanbanStage[] = ['transcript', 'artifacts', 'topics', 'done']

export default function CallDetailPage() {
  const { id: projectId, callId } = useParams<{ id: string; callId: string }>()
  const router = useRouter()
  const [call, setCall] = useState<Call | null>(null)
  const [artifactTypes, setArtifactTypes] = useState<ArtifactType[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [configs, setConfigs] = useState<{ artifact_type_id: string; mode: 'claude' | 'manual' | 'excluded' }[]>([])
  const [transcribing, setTranscribing] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [localOnline, setLocalOnline] = useState(false)
  const [showOfflineModal, setShowOfflineModal] = useState(false)

  useEffect(() => {
    api.calls.get(callId).then(setCall)
    api.artifactTypes.list().then(types => {
      setArtifactTypes(types)
      setConfigs(types.map(t => ({ artifact_type_id: t.id, mode: 'claude' as const })))
    })
    api.artifacts.list(callId).then(setArtifacts)
    checkTranscriptionHealth().then(setLocalOnline)
  }, [callId])

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.name.endsWith('.mp3')) {
      if (!localOnline) { setShowOfflineModal(true); return }
      setTranscribing(true)
      try {
        const result = await transcribeAudio(file)
        const updated = await api.calls.advanceStage(callId, 'artifacts')
        await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/api/calls/${callId}/stage`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stage: 'artifacts' })
        })
        // Store transcript via backend
        const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/api/calls/${callId}`, {
          method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ transcript_text: result.transcript_text, mp3_filename: file.name })
        })
        setCall(await res.json())
      } finally { setTranscribing(false) }
    } else if (file.name.endsWith('.txt')) {
      const text = await file.text()
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/api/calls/${callId}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript_text: text })
      })
      setCall(await res.json())
      const updated = await api.calls.advanceStage(callId, 'artifacts')
      setCall(updated)
    }
  }

  async function handleGenerateArtifacts() {
    const active = configs.filter(c => c.mode !== 'excluded')
    await api.artifacts.generate(callId, active)
    setGenerating(true)

    const es = new EventSource(api.artifacts.streamUrl(callId))
    es.onmessage = (e) => {
      const event: ArtifactSSEEvent = JSON.parse(e.data)
      if (event.type === 'done') { es.close(); setGenerating(false); api.artifacts.list(callId).then(setArtifacts); return }
      if (event.type === 'update' && event.artifact_id) {
        setArtifacts(prev => prev.map(a =>
          a.id === event.artifact_id
            ? { ...a, status: event.status!, content: event.content || a.content, error_message: event.error_message }
            : a
        ))
      }
    }
    es.onerror = () => { es.close(); setGenerating(false) }
  }

  const allArtifactsDone = artifacts.length > 0 && artifacts.every(a => a.status === 'done')

  async function handleAdvanceToTopics() {
    const updated = await api.calls.advanceStage(callId, 'topics')
    setCall(updated)
  }

  if (!call) return <div className="text-gray-500">Loading...</div>

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-2 mb-6 text-sm text-gray-500">
        <a href={`/projects/${projectId}`} className="hover:underline">← Back</a>
        <span>/</span>
        <span className="font-medium text-gray-900">{call.title}</span>
      </div>

      <StageIndicator current={call.kanban_stage} />

      {call.kanban_stage === 'transcript' && (
        <div className="mt-6 p-6 border-2 border-dashed rounded-xl text-center">
          <p className="text-gray-600 mb-4">Load the call transcript</p>
          <label className="cursor-pointer bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
            {transcribing ? 'Transcribing...' : 'Select MP3 or TXT file'}
            <input type="file" accept=".mp3,.txt" className="hidden" onChange={handleFileUpload} disabled={transcribing} />
          </label>
          <p className="text-xs text-gray-400 mt-2">MP3 requires local transcription server to be running</p>
        </div>
      )}

      {call.kanban_stage === 'artifacts' && (
        <div className="mt-6">
          {artifacts.length === 0 ? (
            <>
              <h2 className="font-semibold mb-4">Select artifacts to generate</h2>
              <ArtifactSelector artifactTypes={artifactTypes} configs={configs} onChange={setConfigs} />
              <button onClick={handleGenerateArtifacts} disabled={generating}
                className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50">
                {generating ? 'Generating...' : 'Generate Selected Artifacts'}
              </button>
            </>
          ) : (
            <>
              <h2 className="font-semibold mb-4">Review Artifacts</h2>
              <div className="space-y-4">
                {artifacts.map(a => (
                  <ArtifactCard key={a.id} artifact={a} artifactType={artifactTypes.find(t => t.id === a.artifact_type_id)}
                    onUpdate={updated => setArtifacts(prev => prev.map(x => x.id === updated.id ? updated : x))} />
                ))}
              </div>
              {allArtifactsDone && (
                <button onClick={handleAdvanceToTopics} className="mt-6 bg-green-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-green-700">
                  All Done → Proceed to Topics
                </button>
              )}
            </>
          )}
        </div>
      )}

      {call.kanban_stage === 'topics' && (
        <TopicsStage callId={callId} projectId={projectId} onDone={() => router.push(`/projects/${projectId}`)} />
      )}

      {call.kanban_stage === 'done' && (
        <div className="mt-6 text-center py-12">
          <p className="text-green-600 font-semibold text-lg">✓ Call complete</p>
          <a href={`/projects/${projectId}`} className="text-blue-600 text-sm hover:underline mt-2 block">Back to project</a>
        </div>
      )}

      {showOfflineModal && (
        <OfflineModal onClose={() => setShowOfflineModal(false)} />
      )}
    </div>
  )
}

function StageIndicator({ current }: { current: KanbanStage }) {
  const stages = [
    { key: 'transcript', label: 'Transcript' },
    { key: 'artifacts', label: 'Artifacts' },
    { key: 'topics', label: 'Topics' },
    { key: 'done', label: 'Done' },
  ]
  const currentIdx = stages.findIndex(s => s.key === current)
  return (
    <div className="flex items-center gap-2">
      {stages.map((s, i) => (
        <div key={s.key} className="flex items-center gap-2">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${i < currentIdx ? 'bg-green-500 text-white' : i === currentIdx ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500'}`}>
            {i < currentIdx ? '✓' : i + 1}
          </div>
          <span className={`text-sm ${i === currentIdx ? 'font-medium' : 'text-gray-500'}`}>{s.label}</span>
          {i < stages.length - 1 && <div className="w-8 h-px bg-gray-300" />}
        </div>
      ))}
    </div>
  )
}

function OfflineModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 max-w-sm w-full mx-4">
        <h3 className="font-semibold mb-3">Local transcription server is offline</h3>
        <p className="text-sm text-gray-600 mb-4">To transcribe MP3 files, start the local server:</p>
        <ol className="text-sm space-y-1 mb-4 list-decimal list-inside">
          <li>Open a terminal</li>
          <li>Navigate to the Call Tracker folder</li>
          <li>Run: <code className="bg-gray-100 px-1 rounded">./transcription/run_transcription.sh</code></li>
        </ol>
        <p className="text-sm text-gray-500 mb-4">Or upload a <strong>.txt</strong> transcript file instead.</p>
        <button onClick={onClose} className="w-full bg-blue-600 text-white py-2 rounded-lg text-sm">Got it</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-4] feat: call detail page — transcript + artifact stages"
```

---

### Task 4.5: Topics stage + Topic Dashboard

**Files:**
- Create: `frontend/src/components/topics/TopicsStage.tsx`
- Create: `frontend/src/components/topics/TopicDashboard.tsx`

- [ ] **Step 1: Create TopicsStage.tsx**

```typescript
// frontend/src/components/topics/TopicsStage.tsx
'use client'
import { useState } from 'react'
import { api } from '@/api/backend'
import type { Topic } from '@/types'

interface ExtractedTopic {
  title: string
  summary: string
  follow_up_items: string[]
  is_new?: boolean
}

interface Props {
  callId: string
  projectId: string
  onDone: () => void
}

export default function TopicsStage({ callId, projectId, onDone }: Props) {
  const [mode, setMode] = useState<'choose' | 'extracting' | 'review' | 'manual'>('choose')
  const [extracted, setExtracted] = useState<ExtractedTopic[]>([])
  const [manualTopics, setManualTopics] = useState<{ title: string; summary: string; follow_up_items: string[] }[]>([])

  async function handleExtract() {
    setMode('extracting')
    try {
      const result = await api.topics.extract(callId)
      setExtracted(result.topics)
      setMode('review')
    } catch (e) {
      alert('Topic extraction failed. Try again or use manual mode.')
      setMode('choose')
    }
  }

  async function handleValidate(topics: ExtractedTopic[]) {
    // Save new topics + updates
    const existing = await api.topics.list(projectId)
    const updates = []
    for (const t of topics) {
      let topicId: string
      const match = existing.find(e => e.title.toLowerCase() === t.title.toLowerCase())
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

  if (mode === 'choose') return (
    <div className="mt-6 space-y-4">
      <h2 className="font-semibold">Topics</h2>
      <p className="text-sm text-gray-600">Choose how to process topics for this call:</p>
      <div className="flex gap-4">
        <button onClick={handleExtract} className="flex-1 p-4 border-2 rounded-xl hover:border-blue-500 text-sm">
          <div className="font-medium mb-1">🤖 Extract via Claude</div>
          <div className="text-gray-500">AI analyzes transcript and surfaces key topics</div>
        </button>
        <button onClick={() => setMode('manual')} className="flex-1 p-4 border-2 rounded-xl hover:border-blue-500 text-sm">
          <div className="font-medium mb-1">✏️ Manual</div>
          <div className="text-gray-500">Add topics yourself, no API call</div>
        </button>
      </div>
    </div>
  )

  if (mode === 'extracting') return <div className="mt-6 text-blue-600">Extracting topics...</div>

  if (mode === 'review') return (
    <div className="mt-6">
      <h2 className="font-semibold mb-4">Review Extracted Topics</h2>
      <div className="space-y-3">
        {extracted.map((t, i) => (
          <div key={i} className="p-4 border rounded-lg bg-white">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium text-sm">{t.title}</span>
              {t.is_new && <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">New</span>}
            </div>
            <p className="text-sm text-gray-600">{t.summary}</p>
            {t.follow_up_items.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {t.follow_up_items.map((item, j) => <li key={j} className="text-xs text-gray-500">• {item}</li>)}
              </ul>
            )}
          </div>
        ))}
      </div>
      <button onClick={() => handleValidate(extracted)} className="mt-4 bg-green-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-green-700">
        Confirm & Complete Call
      </button>
    </div>
  )

  if (mode === 'manual') return (
    <div className="mt-6">
      <h2 className="font-semibold mb-4">Add Topics Manually</h2>
      <ManualTopicEditor onValidate={(topics) => handleValidate(topics)} />
    </div>
  )

  return null
}

function ManualTopicEditor({ onValidate }: { onValidate: (topics: any[]) => void }) {
  const [topics, setTopics] = useState([{ title: '', summary: '', follow_up_items: [] as string[] }])

  function addTopic() { setTopics(t => [...t, { title: '', summary: '', follow_up_items: [] }]) }
  function removeTopic(i: number) { setTopics(t => t.filter((_, j) => j !== i)) }
  function update(i: number, field: string, value: string) {
    setTopics(t => t.map((x, j) => j === i ? { ...x, [field]: value } : x))
  }

  return (
    <>
      <div className="space-y-3">
        {topics.map((t, i) => (
          <div key={i} className="p-4 border rounded-lg bg-white">
            <input value={t.title} onChange={e => update(i, 'title', e.target.value)} placeholder="Topic title" className="w-full border rounded px-3 py-2 text-sm mb-2" />
            <textarea value={t.summary} onChange={e => update(i, 'summary', e.target.value)} placeholder="Summary" className="w-full border rounded px-3 py-2 text-sm mb-2 resize-none" rows={2} />
            <button onClick={() => removeTopic(i)} className="text-xs text-red-500 hover:underline">Remove</button>
          </div>
        ))}
      </div>
      <button onClick={addTopic} className="mt-2 text-sm text-blue-600 hover:underline">+ Add topic</button>
      <button onClick={() => onValidate(topics.filter(t => t.title.trim()))}
        className="mt-4 ml-4 bg-green-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-green-700">
        Confirm & Complete Call
      </button>
    </>
  )
}
```

- [ ] **Step 2: Create TopicDashboard.tsx**

```typescript
// frontend/src/components/topics/TopicDashboard.tsx
'use client'
import { useEffect, useState } from 'react'
import { api } from '@/api/backend'
import type { Topic, TopicStatus } from '@/types'

const STATUS_STYLES: Record<TopicStatus, string> = {
  active: 'bg-blue-100 text-blue-700',
  decision_made: 'bg-green-100 text-green-700',
  on_hold: 'bg-yellow-100 text-yellow-700',
  closed: 'bg-gray-100 text-gray-500'
}

const STATUS_LABELS: Record<TopicStatus, string> = {
  active: 'Active',
  decision_made: 'Decision Made',
  on_hold: 'On Hold',
  closed: 'Closed'
}

interface Props { projectId: string }

export default function TopicDashboard({ projectId }: Props) {
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
    const topic = await api.topics.create(projectId, { title: newTitle.trim() })
    setTopics(t => [...t, topic])
    setNewTitle('')
    setAdding(false)
  }

  async function handleStatusChange(topicId: string, status: TopicStatus) {
    const updated = await api.topics.update(topicId, { status })
    setTopics(t => t.map(x => x.id === topicId ? updated : x))
  }

  async function handleDelete(topicId: string) {
    await api.topics.delete(topicId)
    setTopics(t => t.filter(x => x.id !== topicId))
  }

  if (loading) return <div className="text-gray-500">Loading topics...</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="font-semibold">Topic Dashboard</h2>
        <button onClick={() => setAdding(true)} className="text-sm text-blue-600 hover:underline">+ Add topic</button>
      </div>

      {adding && (
        <form onSubmit={handleAdd} className="mb-4 flex gap-2">
          <input autoFocus value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder="Topic title" className="flex-1 border rounded px-3 py-2 text-sm" />
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded text-sm">Add</button>
          <button type="button" onClick={() => setAdding(false)} className="border px-3 py-2 rounded text-sm">Cancel</button>
        </form>
      )}

      {topics.length === 0 ? (
        <p className="text-gray-500 text-center py-12">No topics yet. Topics are added during the Topics stage of each call.</p>
      ) : (
        <div className="space-y-3">
          {topics.map(topic => (
            <div key={topic.id} className="p-4 border rounded-lg bg-white">
              <div className="flex items-start justify-between gap-4">
                <span className="font-medium text-sm">{topic.title}</span>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <select
                    value={topic.status}
                    onChange={e => handleStatusChange(topic.id, e.target.value as TopicStatus)}
                    className={`text-xs px-2 py-1 rounded-full border-0 ${STATUS_STYLES[topic.status]}`}
                  >
                    {(Object.keys(STATUS_LABELS) as TopicStatus[]).map(s => (
                      <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                    ))}
                  </select>
                  <button onClick={() => handleDelete(topic.id)} className="text-xs text-red-400 hover:text-red-600">✕</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-4] feat: topics stage + topic dashboard"
```

---

## Epic 5: Backend call transcript update endpoint

The call detail page needs `PATCH /api/calls/{id}` to store transcript text and mp3_filename after transcription.

### Task 5.1: Add PATCH /api/calls/{call_id} endpoint

**Files:**
- Modify: `backend/api/routes/calls.py`
- Modify: `backend/api/models.py`
- Modify: `backend/tests/test_calls.py`

- [ ] **Step 1: Add CallUpdate model to models.py**

```python
# Add to backend/api/models.py
class CallUpdate(BaseModel):
    transcript_text: Optional[str] = None
    mp3_filename: Optional[str] = None
```

- [ ] **Step 2: Add failing test**

```python
# Add to backend/tests/test_calls.py
@pytest.mark.asyncio
async def test_update_call_transcript():
    with patch("backend.api.routes.calls.get_client") as mock_get:
        mock_client = MagicMock()
        updated = {**MOCK_CALL, "transcript_text": "New transcript"}
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
        mock_get.return_value = mock_client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(f"/api/calls/{CALL_ID}", json={"transcript_text": "New transcript"})
    assert response.status_code == 200
    assert response.json()["transcript_text"] == "New transcript"
```

- [ ] **Step 3: Run test — expect FAIL**

```bash
cd backend && pytest tests/test_calls.py::test_update_call_transcript -v
```

- [ ] **Step 4: Add PATCH endpoint to routes/calls.py**

```python
# Add to backend/api/routes/calls.py
from backend.api.models import CallUpdate  # add to existing import

@router.patch("/api/calls/{call_id}", response_model=CallResponse)
async def update_call(call_id: str, payload: CallUpdate):
    logger.info(f"📥 PATCH /api/calls/{call_id}")
    db = get_client()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    result = db.table("calls").update(updates).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    return result.data[0]
```

- [ ] **Step 5: Run all tests**

```bash
cd backend && pytest -v
```
Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-5] feat: PATCH /api/calls/{id} for transcript storage"
```

---

## Final Steps

### Task 6.1: Wire TranscriptionStatusBadge into layout

**Files:**
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: Add badge to layout**

```typescript
// frontend/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'
import TranscriptionStatusBadge from '@/components/ui/TranscriptionStatusBadge'

export const metadata: Metadata = { title: 'Call Tracker' }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center justify-between">
          <a href="/" className="font-semibold text-gray-900">Call Tracker</a>
          <TranscriptionStatusBadge />
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  )
}
```

- [ ] **Step 2: Run full frontend test suite**

```bash
cd frontend && npx jest --passWithNoTests
```

- [ ] **Step 3: Run full backend test suite**

```bash
cd backend && pytest -v
```

- [ ] **Step 4: Final commit**

```bash
python3 scripts/git_ops.py commit "[FINAL] feat: wire TranscriptionStatusBadge, all tests pass"
python3 scripts/git_ops.py push
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Covered by |
|---|---|
| Kanban pipeline (transcript → artifacts → topics → done) | Tasks 2.1, 4.3, 4.4 |
| MP3 transcription (Whisper + pyannote, local) | Task 3.1 |
| .txt transcript upload | Task 4.4 |
| Sequential call enforcement (one active at a time) | Task 2.1 |
| 6 default artifact types seeded | Task 1.3 |
| Per-artifact mode: Claude / Manual / Excluded | Task 2.3, 4.4 |
| SSE artifact generation | Task 2.3, 4.4 |
| Edit + paste artifact content | Task 4.4 (ArtifactCard) |
| Mark artifact done | Task 2.3, 4.4 |
| Topic extraction: Claude or Manual | Task 2.4, 4.5 |
| Topic CRUD (add/edit/remove/status) | Task 2.4, 4.5 |
| Topic statuses (active/decision_made/on_hold/closed) | Task 2.4, 4.5 |
| Topic Dashboard (project-level aggregation) | Task 4.5 |
| Sequential topic chain (previous call context) | Task 2.4 (claude_service.extract_topics) |
| Editable artifact type prompts | Task 2.2 (PATCH endpoint), 4.1 (API client) |
| Transcription status badge + offline modal | Task 4.2, 4.4, 6.1 |
| Prompt snapshot immutability | Task 2.3 (prompt_used stored at creation) |
| No API call without user action (NFR-08) | Task 4.4 (user selects mode + clicks generate) |
| Claude API key server-side only | Task 2.3 (claude_service in Railway backend) |

**Gap found:** `PATCH /api/calls/{id}` for transcript storage was missing from initial task breakdown → added as Task 5.1.

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `ArtifactMode`, `KanbanStage`, `TopicStatus` defined in `types/index.ts` and used consistently. `ArtifactSSEEvent` matches SSE response shape from `artifacts.py`.
