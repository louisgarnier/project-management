# Multi-LLM Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick which LLM (Groq free / Claude / ChatGPT) generates each artifact — configurable at project level and overridable per artifact type, with a live apply-to-all control in the generation flow.

**Architecture:** The `mode` field on artifact rows (previously `"claude" | "manual"`) now stores the LLM provider (`"groq" | "claude" | "openai" | "manual"`). A new `llm_service.py` dispatches to all three providers using the Anthropic SDK for Claude and the OpenAI SDK (OpenAI-compatible) for Groq and OpenAI. Projects gain a `default_llm` column; artifact types gain a nullable `llm` column (null = inherit project default). The Artifacts Types page exposes both settings; the ArtifactsStage generation flow shows per-artifact LLM dropdowns with an apply-to-all override.

**Tech Stack:** FastAPI + Anthropic SDK + OpenAI SDK (Groq is OpenAI-compatible); Next.js 15 / React 19 / TypeScript / Tailwind v4.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/database/migrations/004_multi_llm.sql` | Create | Add `default_llm` to projects, `llm` to artifact_types |
| `backend/requirements.txt` | Modify | Add `openai>=1.0.0` |
| `backend/.env.example` | Modify | Add `GROQ_API_KEY`, `OPENAI_API_KEY` |
| `backend/services/llm_service.py` | Create | Multi-provider generate: groq / claude / openai |
| `backend/services/claude_service.py` | Delete | Replaced by llm_service.py |
| `backend/routers/artifacts.py` | Modify | mode Literal includes groq/openai; stream fetches mode; calls llm_service |
| `backend/routers/artifact_types.py` | Modify | ArtifactTypeCreate/Update accept `llm` field; use exclude_unset |
| `backend/routers/projects.py` | Modify | GET `/{id}`, PATCH `/{id}` for default_llm |
| `backend/tests/test_llm_service.py` | Create | Unit tests for all three providers |
| `backend/tests/test_artifacts.py` | Modify | Test groq/openai modes |
| `backend/tests/test_artifact_types.py` | Modify | Test `llm` field in create/update |
| `backend/tests/test_projects.py` | Modify | Test GET /{id}, PATCH /{id} |
| `frontend/src/types/index.ts` | Modify | Add `LLMProvider`, update `Project`, `ArtifactType`, `ArtifactMode` |
| `frontend/src/api/client.ts` | Modify | `projectsAPI.get` + `projectsAPI.update`; update `artifactTypesAPI.update`; update `artifactsAPI.createSelections` |
| `frontend/src/components/ArtifactTypeCard.tsx` | Modify | Add LLM dropdown per card |
| `frontend/app/projects/[id]/artifacts/page.tsx` | Modify | Fetch project; project-level LLM dropdown in header |
| `frontend/src/components/ArtifactSelector.tsx` | Modify | Per-row LLM dropdown when Generate selected; export `SelectionMode` |
| `frontend/src/components/ArtifactsStage.tsx` | Modify | Apply-to-all LLM control; pass projectDefaultLlm; init fetches project |

---

## Task 1: DB migration + openai package

**Files:**
- Create: `backend/database/migrations/004_multi_llm.sql`
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

- [ ] **Step 1: Create `backend/database/migrations/004_multi_llm.sql`**

```sql
-- Migration 004: multi-LLM support
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS default_llm TEXT NOT NULL DEFAULT 'groq';

ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS llm TEXT;

-- Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name IN ('projects', 'artifact_types')
  AND column_name IN ('default_llm', 'llm')
ORDER BY table_name, column_name;
```

- [ ] **Step 2: Run the migration in Supabase**

Go to Supabase Dashboard → SQL Editor → paste the SQL above (SELECT only, after the ALTER statements) → Run.
Expected output: 2 rows — `artifact_types.llm` (nullable, no default) and `projects.default_llm` (NOT NULL, default 'groq').

- [ ] **Step 3: Add `openai` to `backend/requirements.txt`**

Add this line after the `anthropic` line:
```
openai>=1.0.0
```

- [ ] **Step 4: Install the new package**

```bash
cd "/Users/louisgarnier/Claude/Project management"
pip install openai 2>&1 | tail -3
```

- [ ] **Step 5: Update `backend/.env.example`**

Replace current content with:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key-here
FRONTEND_URL=http://localhost:3000
LOG_LEVEL=INFO

# LLM providers — add keys for whichever you use
ANTHROPIC_API_KEY=sk-ant-api03-...
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-proj-...
```

- [ ] **Step 6: Update `backend/.env`**

Add to `backend/.env` (do NOT commit this file):
```
GROQ_API_KEY=your-groq-key-here
OPENAI_API_KEY=your-openai-key-here
```

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] chore: multi-LLM migration + openai package"
```

(Stage: `backend/database/migrations/004_multi_llm.sql backend/requirements.txt backend/.env.example`)

---

## Task 2: `llm_service.py` — multi-provider generate

**Files:**
- Create: `backend/services/llm_service.py`
- Create: `backend/tests/test_llm_service.py`
- Delete: `backend/services/claude_service.py`

- [ ] **Step 1: Write failing tests in `backend/tests/test_llm_service.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
@patch("backend.services.llm_service.anthropic.AsyncAnthropic")
async def test_generate_with_claude(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    msg = MagicMock()
    msg.content = [MagicMock(text="Claude output")]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    mock_client.messages.create = AsyncMock(return_value=msg)

    from backend.services.llm_service import generate_artifact
    result = await generate_artifact("prompt", "transcript", "claude")
    assert result == "Claude output"


@pytest.mark.asyncio
@patch("backend.services.llm_service.AsyncOpenAI")
async def test_generate_with_groq(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Groq output"
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    mock_client.chat.completions.create = AsyncMock(return_value=response)

    from backend.services.llm_service import generate_artifact
    result = await generate_artifact("prompt", "transcript", "groq")
    assert result == "Groq output"
    # Verify Groq base_url was used
    call_kwargs = mock_cls.call_args[1]
    assert "groq.com" in call_kwargs["base_url"]


@pytest.mark.asyncio
@patch("backend.services.llm_service.AsyncOpenAI")
async def test_generate_with_openai(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "OpenAI output"
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    mock_client.chat.completions.create = AsyncMock(return_value=response)

    from backend.services.llm_service import generate_artifact
    result = await generate_artifact("prompt", "transcript", "openai")
    assert result == "OpenAI output"
    # Verify no base_url override for OpenAI
    call_kwargs = mock_cls.call_args[1]
    assert "base_url" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_unknown_llm():
    from backend.services.llm_service import generate_artifact
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        await generate_artifact("prompt", "transcript", "unknown")
```

- [ ] **Step 2: Run — verify all 4 FAIL**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/test_llm_service.py -v 2>&1 | tail -10
```

Expected: ImportError or 4 failures.

- [ ] **Step 3: Create `backend/services/llm_service.py`**

```python
import asyncio
import os

import anthropic
from openai import AsyncOpenAI, RateLimitError as OpenAIRateLimitError

from backend.utils.logger import get_logger

logger = get_logger("llm_service")

_MAX_RETRIES = 3  # 3 retries = 4 total attempts


async def generate_artifact(prompt_used: str, transcript: str, llm: str) -> str:
    """
    Generate an artifact using the specified LLM provider.
    llm must be one of: "groq", "claude", "openai".
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
    if llm == "claude":
        return await _generate_claude(prompt_used, transcript)
    elif llm == "groq":
        return await _generate_openai_compat(
            prompt_used, transcript,
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            provider="Groq",
        )
    elif llm == "openai":
        return await _generate_openai_compat(
            prompt_used, transcript,
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=None,
            model="gpt-4o",
            provider="OpenAI",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'claude', or 'openai'.")


async def _generate_claude(prompt_used: str, transcript: str) -> str:
    client = anthropic.AsyncAnthropic()
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 [Claude] Generating artifact (attempt {attempt + 1})")
            message = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                messages=[{"role": "user", "content": user_message}],
            )
            content = message.content[0].text
            logger.info(
                f"✅ [Claude] Generated — "
                f"input={message.usage.input_tokens} output={message.usage.output_tokens}"
            )
            return content
        except anthropic.RateLimitError:
            if attempt == _MAX_RETRIES:
                logger.error("❌ [Claude] Rate limit exhausted after 3 retries")
                raise
            wait = 2 ** attempt
            logger.warning(f"⚠️ [Claude] Rate limited — retrying in {wait}s")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # pragma: no cover


async def _generate_openai_compat(
    prompt_used: str,
    transcript: str,
    api_key: str,
    base_url: str | None,
    model: str,
    provider: str,
) -> str:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(f"🤖 [{provider}] Generating artifact (attempt {attempt + 1})")
            response = await client.chat.completions.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": user_message}],
            )
            content = response.choices[0].message.content or ""
            logger.info(
                f"✅ [{provider}] Generated — "
                f"input={response.usage.prompt_tokens} output={response.usage.completion_tokens}"
            )
            return content
        except OpenAIRateLimitError:
            if attempt == _MAX_RETRIES:
                logger.error(f"❌ [{provider}] Rate limit exhausted after 3 retries")
                raise
            wait = 2 ** attempt
            logger.warning(f"⚠️ [{provider}] Rate limited — retrying in {wait}s")
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # pragma: no cover
```

- [ ] **Step 4: Run — verify all 4 PASS**

```bash
python3 -m pytest backend/tests/test_llm_service.py -v 2>&1 | tail -10
```

Expected: 4/4 pass.

- [ ] **Step 5: Delete `backend/services/claude_service.py`**

```bash
rm "backend/services/claude_service.py"
```

- [ ] **Step 6: Run full suite (expect failures from artifacts.py still importing claude_service)**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -5
```

Expected: some failures — `ImportError: cannot import name 'generate_artifact' from 'backend.services.claude_service'`. This is expected and fixed in Task 3.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: llm_service — groq/claude/openai dispatch"
```

(Stage: `backend/services/llm_service.py backend/tests/test_llm_service.py`)

---

## Task 3: Backend routers — artifacts + artifact_types + projects

**Files:**
- Modify: `backend/routers/artifacts.py`
- Modify: `backend/routers/artifact_types.py`
- Modify: `backend/routers/projects.py`
- Modify: `backend/tests/test_artifacts.py`
- Modify: `backend/tests/test_artifact_types.py`
- Modify: `backend/tests/test_projects.py`

### Part A — artifacts.py

- [ ] **Step 1: Write 2 new failing tests in `backend/tests/test_artifacts.py`**

Add after existing tests:

```python
@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
def test_stream_uses_artifact_mode_as_llm(mock_gen, mock_gc):
    """SSE stream passes artifact.mode to generate_artifact as the llm param."""
    import asyncio
    mock_gen.return_value = asyncio.coroutine(lambda: "output")()

    async def _run():
        mock_gen.reset_mock()
        mock_gen.return_value = "groq output"

        m = MagicMock()
        m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "call-1", "transcript": "transcript text"}
        ]
        m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
            {"id": ART_ID_1, "prompt_used": "do x", "mode": "groq"},
        ]
        m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
        mock_gc.return_value = m

        r = client.get(f"/api/calls/call-1/artifacts/stream",
                       headers={"Accept": "text/event-stream"})
        assert r.status_code == 200
        # generate_artifact must have been called with llm="groq"
        mock_gen.assert_called_once()
        _, _, llm_arg = mock_gen.call_args[0]
        assert llm_arg == "groq"

    asyncio.get_event_loop().run_until_complete(_run())


@patch("backend.routers.artifacts.get_client")
def test_create_selections_accepts_groq_mode(mock_gc):
    """POST /artifacts accepts mode='groq' and stores it."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [{"id": CALL_ID}]
    m.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": TYPE_ID_1, "prompt": "prompt text"}
    ]
    artifact_row = make_artifact(ART_ID_1, TYPE_ID_1, mode="groq", status="pending")
    m.table.return_value.insert.return_value.execute.return_value.data = [artifact_row]
    mock_gc.return_value = m
    r = client.post(f"/api/calls/{CALL_ID}/artifacts",
                    json={"selections": [{"artifact_type_id": TYPE_ID_1, "mode": "groq"}]})
    assert r.status_code == 201
    inserted = m.table.return_value.insert.call_args[0][0]
    assert inserted[0]["mode"] == "groq"
    assert inserted[0]["status"] == "pending"
```

- [ ] **Step 2: Run — verify both FAIL**

```bash
python3 -m pytest backend/tests/test_artifacts.py::test_stream_uses_artifact_mode_as_llm backend/tests/test_artifacts.py::test_create_selections_accepts_groq_mode -v 2>&1 | tail -10
```

- [ ] **Step 3: Update `backend/routers/artifacts.py`**

Read the file. Make these changes:

**Change 1** — Replace import:
```python
# OLD:
from backend.services.claude_service import generate_artifact
# NEW:
from backend.services.llm_service import generate_artifact
```

**Change 2** — Extend mode Literal in `ArtifactSelection`:
```python
class ArtifactSelection(BaseModel):
    artifact_type_id: str
    mode: Literal["groq", "claude", "openai", "manual"]
```

**Change 3** — In `create_artifact_selections`, the `if s.mode == "manual"` block is already correct (manual → done, anything else → pending). No change needed.

**Change 4** — In `stream_artifacts`, update the SELECT to include `mode`:
```python
artifacts_result = (
    supabase.table("artifacts")
    .select("id,prompt_used,mode")
    .eq("call_id", call_id)
    .eq("status", "pending")
    .execute()
)
```

**Change 5** — In `gen_one`, pass `artifact["mode"]` as the `llm` arg:
```python
content = await generate_artifact(prompt_used, transcript, artifact["mode"])
```

- [ ] **Step 4: Run new tests + full suite**

```bash
python3 -m pytest backend/tests/test_artifacts.py -v 2>&1 | tail -15
python3 -m pytest backend/tests/ -q 2>&1 | tail -5
```

Expected: all artifacts tests pass; total count now includes llm_service tests.

### Part B — artifact_types.py

- [ ] **Step 5: Write failing test in `backend/tests/test_artifact_types.py`**

Add after existing tests:

```python
@patch("backend.routers.artifact_types.get_client")
def test_create_artifact_type_with_llm(mock_gc):
    """POST artifact type accepts optional llm field."""
    m = MagicMock()
    created = {
        "id": str(uuid4()), "project_id": str(uuid4()),
        "name": "My Type", "prompt": "do x", "is_default": False,
        "llm": "groq", "created_at": "2026-01-01T00:00:00",
    }
    m.table.return_value.insert.return_value.execute.return_value.data = [created]
    mock_gc.return_value = m
    r = client.post(f"/api/projects/{created['project_id']}/artifact-types",
                    json={"name": "My Type", "prompt": "do x", "llm": "groq"})
    assert r.status_code == 201
    inserted = m.table.return_value.insert.call_args[0][0]
    assert inserted["llm"] == "groq"


@patch("backend.routers.artifact_types.get_client")
def test_update_artifact_type_reset_llm_to_null(mock_gc):
    """PATCH artifact type can set llm to null (reset to project default)."""
    type_id = str(uuid4())
    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {"id": type_id}
    ]
    updated = {
        "id": type_id, "project_id": project_id,
        "name": "My Type", "prompt": "do x", "is_default": False,
        "llm": None, "created_at": "2026-01-01T00:00:00",
    }
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [updated]
    mock_gc.return_value = m
    r = client.patch(f"/api/projects/{project_id}/artifact-types/{type_id}",
                     json={"llm": None})
    assert r.status_code == 200
    update_payload = m.table.return_value.update.call_args[0][0]
    assert "llm" in update_payload
    assert update_payload["llm"] is None
```

- [ ] **Step 6: Run — verify both FAIL**

```bash
python3 -m pytest backend/tests/test_artifact_types.py::test_create_artifact_type_with_llm backend/tests/test_artifact_types.py::test_update_artifact_type_reset_llm_to_null -v 2>&1 | tail -10
```

- [ ] **Step 7: Update `backend/routers/artifact_types.py`**

Read the file. Make these changes:

**Change 1** — Add `Literal` to imports:
```python
from pydantic import BaseModel, Field
from typing import Literal
```

**Change 2** — Update `ArtifactTypeCreate` to accept optional `llm`:
```python
class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    llm: Literal["groq", "claude", "openai"] | None = None
```

**Change 3** — Update `ArtifactTypeUpdate` to accept optional `llm` (including null to reset):
```python
class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "claude", "openai"] | None = Field(default=..., exclude=False)

    model_config = {"arbitrary_types_allowed": True}
```

Wait — the challenge here is distinguishing "llm not sent" from "llm: null sent". Use `model_dump(exclude_unset=True)` instead of `if v is not None`.

**Change 3 (correct)** — Update `ArtifactTypeUpdate`:
```python
class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "claude", "openai"] | None = Field(default=None)
```

**Change 4** — In `update_artifact_type`, use `exclude_unset=True` instead of `if v is not None`:
```python
update = payload.model_dump(exclude_unset=True)
if not update:
    raise HTTPException(status_code=422, detail="No fields to update")
```

**Change 5** — In `create_artifact_type`, include `llm` in the insert:
```python
result = (
    client.table("artifact_types")
    .insert({
        "project_id": project_id,
        "name": payload.name,
        "prompt": payload.prompt,
        "is_default": False,
        "llm": payload.llm,
    })
    .execute()
)
```

**Change 6** — In `import_artifact_types`, include `llm` from source:
```python
source = (
    client.table("artifact_types")
    .select("name,prompt,llm")
    .in_("id", payload.type_ids)
    .execute()
)
copies = [
    {
        "project_id": project_id,
        "name": t["name"],
        "prompt": t["prompt"],
        "is_default": False,
        "llm": t.get("llm"),
    }
    for t in source.data
]
```

### Part C — projects.py

- [ ] **Step 8: Write failing tests in `backend/tests/test_projects.py`**

Add after existing tests:

```python
@patch("backend.routers.projects.get_client")
def test_get_project_by_id(mock_gc):
    """GET /api/projects/{id} returns the project."""
    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": project_id, "name": "Test", "description": "", "default_llm": "groq", "created_at": "2026-01-01"}
    ]
    mock_gc.return_value = m
    r = client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["id"] == project_id


@patch("backend.routers.projects.get_client")
def test_get_project_not_found(mock_gc):
    """GET /api/projects/{id} returns 404 for unknown project."""
    m = MagicMock()
    m.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_gc.return_value = m
    r = client.get(f"/api/projects/{uuid4()}")
    assert r.status_code == 404


@patch("backend.routers.projects.get_client")
def test_update_project_default_llm(mock_gc):
    """PATCH /api/projects/{id} updates default_llm."""
    project_id = str(uuid4())
    m = MagicMock()
    m.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [
        {"id": project_id, "name": "Test", "description": "", "default_llm": "claude", "created_at": "2026-01-01"}
    ]
    mock_gc.return_value = m
    r = client.patch(f"/api/projects/{project_id}", json={"default_llm": "claude"})
    assert r.status_code == 200
    assert r.json()["default_llm"] == "claude"


@patch("backend.routers.projects.get_client")
def test_update_project_invalid_llm(mock_gc):
    """PATCH /api/projects/{id} rejects unknown LLM values."""
    mock_gc.return_value = MagicMock()
    r = client.patch(f"/api/projects/{uuid4()}", json={"default_llm": "unknown"})
    assert r.status_code == 422
```

- [ ] **Step 9: Run — verify all 4 FAIL**

```bash
python3 -m pytest backend/tests/test_projects.py::test_get_project_by_id backend/tests/test_projects.py::test_get_project_not_found backend/tests/test_projects.py::test_update_project_default_llm backend/tests/test_projects.py::test_update_project_invalid_llm -v 2>&1 | tail -10
```

- [ ] **Step 10: Update `backend/routers/projects.py`**

Read the file. Add `Literal` to imports and add two new endpoints:

```python
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.database.supabase_client import get_client
from backend.routers.artifact_types import seed_defaults
from backend.utils.logger import db_logger, get_logger

logger = get_logger("projects")
router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    default_llm: Literal["groq", "claude", "openai"]


@router.get("")
def list_projects():
    client = get_client()
    db_logger.info("🗄️ [DB] Fetching all projects")
    result = client.table("projects").select("*").execute()
    db_logger.info(f"✅ [DB] Retrieved {len(result.data)} projects")
    return result.data


@router.post("", status_code=201)
def create_project(payload: ProjectCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating project: {payload.name}")
    result = client.table("projects").insert(payload.model_dump()).execute()
    project = result.data[0]
    db_logger.info(f"✅ [DB] Created project: {project['id']}")
    seed_defaults(project["id"])
    return project


@router.get("/{project_id}")
def get_project(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching project: {project_id}")
    result = client.table("projects").select("*").eq("id", project_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data[0]


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Updating project: {project_id}")
    result = (
        client.table("projects")
        .update(payload.model_dump())
        .eq("id", project_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    db_logger.info(f"✅ [DB] Updated project: {project_id}")
    return result.data[0]


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Deleting project: {project_id}")
    result = client.table("projects").delete().eq("id", project_id).execute()
    if not result.data:
        db_logger.warning(f"⚠️ [DB] Project not found: {project_id}")
        raise HTTPException(status_code=404, detail="Project not found")
    db_logger.info(f"✅ [DB] Deleted project: {project_id}")
    return Response(status_code=204)
```

- [ ] **Step 11: Run full suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -5
```

Expected: all tests pass. Count should be 58 (existing) + 4 (llm_service) + 2 (artifacts) + 2 (artifact_types) + 4 (projects) = 70 passed.

- [ ] **Step 12: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: multi-LLM backend — artifacts/artifact_types/projects routers"
```

---

## Task 4: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update `frontend/src/types/index.ts`**

Read the file. Make these changes:

**Change 1** — Add `LLMProvider` type and update `Project`:
```typescript
export type LLMProvider = "groq" | "claude" | "openai";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider;
  created_at: string;
}
```

**Change 2** — Update `ArtifactType` to include `llm`:
```typescript
export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  llm: LLMProvider | null;
  created_at: string;
}
```

**Change 3** — Update `ArtifactMode` to include all providers:
```typescript
export type ArtifactMode = LLMProvider | "manual";
```

- [ ] **Step 2: Update `frontend/src/api/client.ts`**

Read the file. Make these changes:

**Change 1** — Add `LLMProvider` to imports:
```typescript
import type { Project, Call, CallFile, ArtifactType, Artifact, LLMProvider } from "@/types";
```

**Change 2** — Add `get` and `update` to `projectsAPI`:
```typescript
export const projectsAPI = {
  list: () => proxyFetch<Project[]>("/api/projects"),
  get: (id: string) => proxyFetch<Project>(`/api/projects/${id}`),
  create: (data: { name: string; description: string }) =>
    proxyFetch<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: { default_llm: LLMProvider }) =>
    proxyFetch<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) => proxyFetch<void>(`/api/projects/${id}`, { method: "DELETE" }),
};
```

**Change 3** — Update `artifactTypesAPI.update` to accept `llm`:
```typescript
  update: (
    projectId: string,
    typeId: string,
    data: { name?: string; prompt?: string; llm?: LLMProvider | null }
  ) =>
    proxyFetch<ArtifactType>(`/api/projects/${projectId}/artifact-types/${typeId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
```

**Change 4** — Update `artifactsAPI.createSelections` mode type:
```typescript
  createSelections: (
    callId: string,
    selections: { artifact_type_id: string; mode: ArtifactMode }[]
  ) =>
```

- [ ] **Step 3: Lint**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npm run lint 2>&1 | tail -10
```

Expected: 0 errors. (TypeScript errors about `ArtifactMode` mismatch in existing components will surface in Tasks 5–6 when those files are updated.)

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: frontend types + API client for multi-LLM"
```

---

## Task 5: Artifacts page + ArtifactTypeCard — project default + per-type LLM

**Files:**
- Modify: `frontend/app/projects/[id]/artifacts/page.tsx`
- Modify: `frontend/src/components/ArtifactTypeCard.tsx`

### LLM label helper

Both files use this — define it once in each file (don't extract to a shared util, YAGNI):

```typescript
const LLM_LABELS: Record<string, string> = {
  groq: "Groq (free)",
  claude: "Claude",
  openai: "ChatGPT (OpenAI)",
};
```

### artifacts/page.tsx

- [ ] **Step 1: Update `frontend/app/projects/[id]/artifacts/page.tsx`**

Read the file. Make these changes:

**Change 1** — Add imports:
```typescript
import { artifactTypesAPI, projectsAPI } from "@/api/client";
import type { ArtifactType, LLMProvider, Project } from "@/types";
```

**Change 2** — Add `project` state and `savingLlm` state after existing state:
```typescript
const [project, setProject] = useState<Project | null>(null);
const [savingLlm, setSavingLlm] = useState(false);
```

**Change 3** — Update `load` to also fetch the project:
```typescript
const load = useCallback(async () => {
  setLoading(true);
  setError(null);
  try {
    logger.info("Fetching artifact types", { component: "ArtifactsPage", data: { projectId } });
    const [data, proj] = await Promise.all([
      artifactTypesAPI.list(projectId),
      projectsAPI.get(projectId),
    ]);
    setTypes(data);
    setProject(proj);
  } catch (err) {
    logger.error("Failed to load", { component: "ArtifactsPage", data: err });
    setError("Failed to load artifact types.");
  } finally {
    setLoading(false);
  }
}, [projectId]);
```

**Change 4** — Add `handleUpdateDefaultLlm` function:
```typescript
async function handleUpdateDefaultLlm(llm: LLMProvider) {
  if (!project) return;
  setSavingLlm(true);
  try {
    const updated = await projectsAPI.update(projectId, { default_llm: llm });
    setProject(updated);
    logger.info("Updated project default LLM", { component: "ArtifactsPage", data: { llm } });
  } catch (err) {
    logger.error("Failed to update default LLM", { component: "ArtifactsPage", data: err });
  } finally {
    setSavingLlm(false);
  }
}
```

**Change 5** — Update `handleUpdate` signature to accept `llm`:
```typescript
async function handleUpdate(typeId: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null }) {
  const updated = await artifactTypesAPI.update(projectId, typeId, data);
  setTypes((prev) => prev.map((t) => (t.id === typeId ? updated : t)));
}
```

**Change 6** — Replace the header section with the project default LLM dropdown:
```tsx
<div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
  <h1 className="text-[18px] font-bold text-[#172b4d]">Artifact Types</h1>
  <div className="flex items-center gap-3">
    {project && (
      <div className="flex items-center gap-2">
        <span className="text-[11px] text-[#5e6c84]">Project default:</span>
        <select
          value={project.default_llm}
          onChange={(e) => handleUpdateDefaultLlm(e.target.value as LLMProvider)}
          disabled={savingLlm}
          className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] disabled:opacity-50"
        >
          <option value="groq">Groq (free)</option>
          <option value="claude">Claude</option>
          <option value="openai">ChatGPT (OpenAI)</option>
        </select>
      </div>
    )}
    <button
      onClick={() => setShowModal(true)}
      className="bg-[#0052cc] text-white px-4 py-[6px] rounded text-[13px] font-medium hover:bg-[#0065ff]"
    >
      + Add artifact type
    </button>
  </div>
</div>
```

**Change 7** — Pass `projectDefaultLlm` and updated `onUpdate` to `ArtifactTypeCard`:
```tsx
{types.map((t) => (
  <ArtifactTypeCard
    key={t.id}
    type={t}
    projectDefaultLlm={project?.default_llm ?? "groq"}
    onDelete={handleDelete}
    onUpdate={handleUpdate}
  />
))}
```

### ArtifactTypeCard.tsx

- [ ] **Step 2: Update `frontend/src/components/ArtifactTypeCard.tsx`**

Read the file. Make these changes:

**Change 1** — Add imports:
```typescript
import type { ArtifactType, LLMProvider } from "@/types";
```

**Change 2** — Update Props:
```typescript
type Props = {
  type: ArtifactType;
  projectDefaultLlm: LLMProvider;
  onDelete: (id: string) => void;
  onUpdate: (id: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null }) => Promise<void>;
};
```

**Change 3** — Add `llm` state after existing state declarations:
```typescript
const [llm, setLlm] = useState<LLMProvider | null>(type.llm);
```

**Change 4** — Update `handleCancelEdit` to reset llm:
```typescript
function handleCancelEdit() {
  setEditing(false);
  setName(type.name);
  setPrompt(type.prompt);
  setLlm(type.llm);
  setSaveError(null);
}
```

**Change 5** — Update `handleSave` to include llm:
```typescript
async function handleSave() {
  setSaving(true);
  setSaveError(null);
  try {
    await onUpdate(type.id, { name, prompt, llm });
    setEditing(false);
  } catch (err) {
    setSaveError(err instanceof Error ? err.message : "Failed to save");
  } finally {
    setSaving(false);
  }
}
```

**Change 6** — Add LLM dropdown in the expanded edit section, after the prompt textarea.

In the non-editing expanded view, add after the prompt `<p>`:
```tsx
<div className="mt-2 flex items-center gap-2">
  <span className="text-[10px] text-[#97a0af] uppercase tracking-wide">LLM:</span>
  <span className="text-[11px] text-[#5e6c84]">
    {type.llm
      ? { groq: "Groq (free)", claude: "Claude", openai: "ChatGPT (OpenAI)" }[type.llm]
      : `Project default (${{ groq: "Groq (free)", claude: "Claude", openai: "ChatGPT (OpenAI)" }[projectDefaultLlm]})`
    }
  </span>
</div>
```

In the editing expanded section, add after the prompt `<textarea>`:
```tsx
<div className="mt-2 flex items-center gap-2">
  <span className="text-[11px] text-[#5e6c84] flex-shrink-0">LLM:</span>
  <select
    value={llm ?? ""}
    onChange={(e) => setLlm((e.target.value as LLMProvider) || null)}
    className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
  >
    <option value="">Project default ({
      { groq: "Groq (free)", claude: "Claude", openai: "ChatGPT (OpenAI)" }[projectDefaultLlm]
    })</option>
    <option value="groq">Groq (free)</option>
    <option value="claude">Claude</option>
    <option value="openai">ChatGPT (OpenAI)</option>
  </select>
</div>
```

- [ ] **Step 3: Lint**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npm run lint 2>&1 | tail -10
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: project default LLM + per-type LLM on artifacts page"
```

---

## Task 6: ArtifactsStage + ArtifactSelector — LLM in generation flow

**Files:**
- Modify: `frontend/src/components/ArtifactSelector.tsx`
- Modify: `frontend/src/components/ArtifactsStage.tsx`

### ArtifactSelector.tsx

- [ ] **Step 1: Rewrite `frontend/src/components/ArtifactSelector.tsx`**

Read the file. Replace the entire content with:

```typescript
"use client";

import type { ArtifactType, LLMProvider } from "@/types";

// SelectionMode: the LLM provider means "generate with this LLM"; "manual" and "skip" are special
export type SelectionMode = LLMProvider | "manual" | "skip";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "groq", label: "Groq (free)" },
  { value: "claude", label: "Claude" },
  { value: "openai", label: "ChatGPT" },
];

type Props = {
  artifactTypes: ArtifactType[];
  selections: Record<string, SelectionMode>;
  projectDefaultLlm: LLMProvider;
  onChange: (typeId: string, mode: SelectionMode) => void;
};

export default function ArtifactSelector({
  artifactTypes,
  selections,
  projectDefaultLlm,
  onChange,
}: Props) {
  return (
    <div className="flex flex-col gap-2">
      {artifactTypes.map((t) => {
        const sel = selections[t.id] ?? t.llm ?? projectDefaultLlm;
        const isGenerate = sel !== "manual" && sel !== "skip";
        const activeLlm: LLMProvider = isGenerate ? (sel as LLMProvider) : (t.llm ?? projectDefaultLlm);

        return (
          <div
            key={t.id}
            className="flex items-center justify-between gap-3 px-4 py-3 border border-[#dfe1e6] rounded-lg bg-white"
          >
            <span className="text-[13px] font-medium text-[#172b4d] flex-1 min-w-0 truncate">
              {t.name}
            </span>

            {/* Generate / Manual / Skip toggles */}
            <div className="flex gap-1 flex-shrink-0">
              {(["generate", "manual", "skip"] as const).map((btn) => {
                const active =
                  btn === "generate" ? isGenerate : sel === btn;
                return (
                  <button
                    key={btn}
                    onClick={() => {
                      if (btn === "generate") onChange(t.id, activeLlm);
                      else onChange(t.id, btn);
                    }}
                    className={`px-3 py-1.5 text-[11px] font-medium rounded transition-colors capitalize ${
                      active
                        ? btn === "skip"
                          ? "bg-[#f4f5f7] text-[#5e6c84] border border-[#97a0af]"
                          : "bg-[#e9f0ff] text-[#0052cc] border border-[#0052cc]"
                        : "bg-white text-[#5e6c84] border border-[#dfe1e6] hover:bg-[#f4f5f7]"
                    }`}
                  >
                    {btn}
                  </button>
                );
              })}
            </div>

            {/* LLM dropdown — only when Generate is active */}
            {isGenerate && (
              <select
                value={activeLlm}
                onChange={(e) => onChange(t.id, e.target.value as LLMProvider)}
                className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1.5 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] flex-shrink-0"
              >
                {LLM_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

### ArtifactsStage.tsx

- [ ] **Step 2: Update `frontend/src/components/ArtifactsStage.tsx`**

Read the file. Make these changes:

**Change 1** — Update imports:
```typescript
import { artifactTypesAPI, artifactsAPI, callsAPI, projectsAPI } from "@/api/client";
import type { Artifact, ArtifactMode, ArtifactType, Call, LLMProvider } from "@/types";
import ArtifactSelector, { type SelectionMode } from "@/components/ArtifactSelector";
```

**Change 2** — Add `projectDefaultLlm` and `applyLlm` state:
```typescript
const [projectDefaultLlm, setProjectDefaultLlm] = useState<LLMProvider>("groq");
const [applyLlm, setApplyLlm] = useState<LLMProvider>("groq");
```

**Change 3** — Update `selections` type in state:
```typescript
const [selections, setSelections] = useState<Record<string, SelectionMode>>({});
```

**Change 4** — Update `init` to also fetch project and use each type's stored llm as default:
```typescript
const init = useCallback(async () => {
  try {
    const [types, existing, project] = await Promise.all([
      artifactTypesAPI.list(projectId),
      artifactsAPI.list(callId),
      projectsAPI.get(projectId),
    ]);
    setArtifactTypes(types);
    setProjectDefaultLlm(project.default_llm);
    setApplyLlm(project.default_llm);

    // Default each type to its stored llm, or the project default
    const defaultSels: Record<string, SelectionMode> = {};
    types.forEach((t) => {
      defaultSels[t.id] = t.llm ?? project.default_llm;
    });
    setSelections(defaultSels);

    if (existing.length > 0) {
      setArtifacts(existing);
      setPhase("reviewing");
    }
  } catch (err) {
    logger.error("Failed to init ArtifactsStage", { component: "ArtifactsStage", data: err });
  }
}, [projectId, callId]);
```

**Change 5** — Add `handleApplyToAll` function before `handleGenerate`:
```typescript
function handleApplyToAll() {
  setSelections((prev) => {
    const next = { ...prev };
    Object.keys(next).forEach((id) => {
      if (next[id] !== "manual" && next[id] !== "skip") {
        next[id] = applyLlm;
      }
    });
    return next;
  });
}
```

**Change 6** — Update `handleGenerate` payload mapping (LLM provider values map to `mode` directly; "skip" is already filtered):
```typescript
const payload = nonSkipped.map(([typeId, mode]) => ({
  artifact_type_id: typeId,
  mode: mode as ArtifactMode,  // "groq" | "claude" | "openai" | "manual"
}));
```

**Change 7** — Update `ArtifactSelector` usage in render to pass new props:
```tsx
<ArtifactSelector
  artifactTypes={artifactTypes}
  selections={selections}
  projectDefaultLlm={projectDefaultLlm}
  onChange={handleSelectionChange}
/>
```

**Change 8** — Add apply-to-all controls above the ArtifactSelector in the select phase:

Replace the `<div>` header section in the select phase with:
```tsx
<div>
  <h2 className="text-[15px] font-semibold text-[#172b4d] mb-1">Select artifacts to generate</h2>
  <p className="text-[12px] text-[#5e6c84]">
    Choose how each artifact type should be handled for this call.
  </p>
</div>

{artifactTypes.length > 0 && (
  <div className="flex items-center gap-2 px-4 py-2 bg-[#f4f5f7] rounded-lg border border-[#dfe1e6]">
    <span className="text-[11px] text-[#5e6c84]">Apply to all generate:</span>
    <select
      value={applyLlm}
      onChange={(e) => setApplyLlm(e.target.value as LLMProvider)}
      className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
    >
      <option value="groq">Groq (free)</option>
      <option value="claude">Claude</option>
      <option value="openai">ChatGPT (OpenAI)</option>
    </select>
    <button
      onClick={handleApplyToAll}
      className="px-3 py-1 text-[11px] font-medium text-[#0052cc] border border-[#0052cc] rounded hover:bg-[#e9f0ff] transition-colors"
    >
      Apply to all
    </button>
  </div>
)}
```

- [ ] **Step 3: Lint**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npm run lint 2>&1 | tail -10
```

Expected: 0 errors.

- [ ] **Step 4: Run full backend suite**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/ -q 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: multi-LLM selector + apply-to-all in ArtifactsStage"
```

---

## Task 7: Close story + update docs

**Files:**
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/codebase.md`

- [ ] **Step 1: Append to `build-log.md`** — session entry for multi-LLM feature
- [ ] **Step 2: Update `codebase.md`** — add `llm_service.py`, note `claude_service.py` deleted, note new fields
- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] chore: docs update for multi-LLM feature"
```

---

## Self-Review

**Spec coverage:**
- ✅ Project-level LLM dropdown on Artifacts Types page (next to "+ Add")
- ✅ Per-type LLM dropdown on each ArtifactTypeCard (visible when expanded, editable when editing)
- ✅ LLM saved to `artifact_types.llm` (null = project default)
- ✅ Project default saved to `projects.default_llm`
- ✅ In generate flow: per-artifact LLM dropdown defaulting to type's stored LLM
- ✅ "Apply to all" control applies selected LLM to all Generate rows
- ✅ API keys in `.env` only (not in UI)
- ✅ Providers: Groq / Claude / ChatGPT (OpenAI)
- ✅ Backend dispatches to correct provider based on artifact.mode

**No placeholders found.**

**Type consistency check:**
- `LLMProvider = "groq" | "claude" | "openai"` — consistent across types.ts, client.ts, routers
- `ArtifactMode = LLMProvider | "manual"` — DB values (no "skip")
- `SelectionMode = LLMProvider | "manual" | "skip"` — UI-only, from ArtifactSelector
- `ArtifactSelection.mode: Literal["groq", "claude", "openai", "manual"]` — backend Pydantic
- `generate_artifact(prompt, transcript, llm: str)` — llm is the mode value, dispatches by string
