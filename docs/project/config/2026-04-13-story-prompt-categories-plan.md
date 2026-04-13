# Prompt Categories (artifacts vs topics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `category` field (`"artifacts"` | `"topics"`) to `artifact_types`, seed a default topics-extraction prompt per project, and make the topics backend use the project's stored prompt instead of a hardcoded string.

**Architecture:** One DB migration adds `category TEXT NOT NULL DEFAULT 'artifacts'` to `artifact_types`. The backend seeds a `category='topics'` row alongside the existing 6 artifact rows at project-creation time. `_extract_topics_impl` looks up the project's topics prompt before calling Claude. The Artifacts page filters to `category='artifacts'` and shows the topics prompt in a separate read-only section. `"Custom"` labels are renamed to `"Artifacts"` throughout.

**Tech Stack:** PostgreSQL (Supabase), FastAPI + Pydantic v2, Python unittest.mock, Next.js 15 App Router, TypeScript, inline styles.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `backend/database/migrations/005_artifact_type_category.sql` | Add `category` column, backfill existing rows |
| Modify | `backend/routers/artifact_types.py` | Add `category` to seed, expose on read, guard on write |
| Modify | `backend/services/topics_service.py` | Look up project's topics prompt before calling Claude |
| Modify | `backend/tests/test_artifact_types.py` | Add `category` to mock data, add test for topics prompt seeding |
| Modify | `backend/tests/test_topics.py` | Add test that extraction uses project prompt |
| Modify | `frontend/src/types/index.ts` | Add `category` field to `ArtifactType` |
| Modify | `frontend/src/api/client.ts` | No change needed — PATCH already passes through arbitrary fields |
| Modify | `frontend/app/projects/[id]/artifacts/page.tsx` | Split list into artifacts vs topics section; rename "Custom" → "Artifacts" |
| Modify | `frontend/src/components/ArtifactTypeCard.tsx` | Rename "Custom" → "Artifacts" badge |

---

## Task 1: DB migration — add `category` column

**Files:**
- Create: `backend/database/migrations/005_artifact_type_category.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- 005_artifact_type_category.sql
-- Add category to artifact_types: 'artifacts' (default) or 'topics'

ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'artifacts'
  CHECK (category IN ('artifacts', 'topics'));
```

- [ ] **Step 2: Run it in the Supabase dashboard**

Copy the SQL above and run it in the Supabase SQL editor. Expected: no error, column added.

- [ ] **Step 3: Commit the migration file**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] chore: migration 005 — artifact_type category column"
```

---

## Task 2: Backend — seed topics prompt + expose category on API

**Files:**
- Modify: `backend/routers/artifact_types.py`
- Modify: `backend/tests/test_artifact_types.py`

### Context

`seed_defaults(project_id)` currently inserts 6 rows from `DEFAULT_ARTIFACT_TYPES` (all without `category`, so they get the DB default `'artifacts'`). We need to also insert one `category='topics'` row.

The topics extraction prompt to seed:

```
You are an expert at extracting business topics from client call transcripts.

Extract all key business topics discussed. For each topic return a JSON object matching:
{"name":"string","summary":"string","follow_up_items":["string"],"decisions":["string"],"status":"open|in_progress|resolved","owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}

Focus on: decisions made, open questions, action items, relationship dynamics, technical blockers.
Be specific — "Pricing" not "Discussion", "API Integration Timeline" not "Technical".
```

### Steps

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_artifact_types.py`, add at the end:

```python
@patch("backend.routers.artifact_types.get_client")
def test_seed_defaults_inserts_topics_prompt(mock_gc):
    """seed_defaults must insert exactly one category='topics' row."""
    from backend.routers.artifact_types import seed_defaults
    m = MagicMock()
    mock_gc.return_value = m
    seed_defaults("proj-1")
    # collect all insert calls
    all_rows = []
    for call in m.table.return_value.insert.call_args_list:
        rows = call.args[0] if call.args else call.kwargs.get("json", [])
        if isinstance(rows, list):
            all_rows.extend(rows)
        else:
            all_rows.append(rows)
    topics_rows = [r for r in all_rows if r.get("category") == "topics"]
    assert len(topics_rows) == 1, f"Expected 1 topics row, got {len(topics_rows)}"
    assert "name" in topics_rows[0]
    assert "prompt" in topics_rows[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/test_artifact_types.py::test_seed_defaults_inserts_topics_prompt -v
```

Expected: FAIL — topics_rows is empty (no category='topics' row currently seeded).

- [ ] **Step 3: Implement**

In `backend/routers/artifact_types.py`, add after `DEFAULT_ARTIFACT_TYPES`:

```python
DEFAULT_TOPICS_PROMPT = {
    "name": "Topics Extraction",
    "prompt": (
        "You are an expert at extracting business topics from client call transcripts.\n\n"
        "Extract all key business topics discussed. For each topic return a JSON object matching:\n"
        '{"name":"string","summary":"string","follow_up_items":["string"],'
        '"decisions":["string"],"status":"open|in_progress|resolved",'
        '"owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}\n\n'
        "Focus on: decisions made, open questions, action items, relationship dynamics, "
        "technical blockers.\n"
        "Be specific — \"Pricing\" not \"Discussion\", "
        "\"API Integration Timeline\" not \"Technical\"."
    ),
    "is_default": True,
    "category": "topics",
}
```

Then update `seed_defaults`:

```python
def seed_defaults(project_id: str) -> None:
    """Insert 6 default artifact types + 1 topics prompt for a newly created project."""
    client = get_client()
    artifact_rows = [{"project_id": project_id, "category": "artifacts", **t} for t in DEFAULT_ARTIFACT_TYPES]
    client.table("artifact_types").insert(artifact_rows).execute()
    topics_row = {"project_id": project_id, **DEFAULT_TOPICS_PROMPT}
    client.table("artifact_types").insert(topics_row).execute()
    db_logger.info(f"✅ [DB] Seeded 6 artifact types + 1 topics prompt for project: {project_id}")
```

Also update `create_artifact_type` to hardcode `category='artifacts'` (user-created types are always artifacts):

```python
@router.post("/projects/{project_id}/artifact-types", status_code=201)
def create_artifact_type(project_id: str, payload: ArtifactTypeCreate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Creating artifact type for project: {project_id}")
    result = (
        client.table("artifact_types")
        .insert({
            "project_id": project_id,
            "name": payload.name,
            "prompt": payload.prompt,
            "is_default": False,
            "category": "artifacts",
            "llm": payload.llm,
        })
        .execute()
    )
    db_logger.info(f"✅ [DB] Created artifact type: {result.data[0]['id']}")
    return result.data[0]
```

Also update `import_artifact_types` to always copy as `category='artifacts'`:

```python
copies = [
    {
        "project_id": project_id,
        "name": t["name"],
        "prompt": t["prompt"],
        "is_default": False,
        "category": "artifacts",
        "llm": t.get("llm"),
    }
    for t in source.data
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest backend/tests/test_artifact_types.py::test_seed_defaults_inserts_topics_prompt -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: same pass count as before ± the new test. Fix any regressions before continuing.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: seed topics prompt per project, category field on artifact_types"
```

---

## Task 3: Backend — topics service reads prompt from DB

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/tests/test_topics.py`

### Context

Currently `_extract_topics_impl` uses `_EXTRACT_SYSTEM` (hardcoded system prompt) and builds the user prompt inline with `_TOPIC_SCHEMA` baked in. We want:

1. Look up the project's `category='topics'` artifact_type row to get its `prompt` field.
2. Use that as the base of the user prompt (instead of the hardcoded strings).
3. Fall back to the current hardcoded prompt if no row found (safety net for existing projects that were seeded before this migration).

The `_EXTRACT_SYSTEM` constant stays — it's the Claude system role, not the user-facing instructions. Only the user prompt body changes.

### Steps

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_topics.py`, add:

```python
def test_extract_uses_project_topics_prompt():
    """extract_topics must use the stored topics prompt, not a hardcoded string."""
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock

    project_prompt = "CUSTOM TOPICS PROMPT: extract everything."

    mock_db = MagicMock()
    # calls table: return call row
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"project_id": "proj-1", "transcript": "We discussed pricing."}
    ]

    call_count = [0]
    def table_side_effect(name):
        m = MagicMock()
        if name == "calls":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {"project_id": "proj-1", "transcript": "We discussed pricing."}
            ]
        elif name == "artifacts":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        elif name == "artifact_types":
            m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                {"prompt": project_prompt}
            ]
        return m

    mock_db.table.side_effect = table_side_effect

    captured = {}

    async def fake_call_claude(prompt):
        captured["prompt"] = prompt
        return []

    with patch("backend.services.topics_service.get_client", return_value=mock_db), \
         patch("backend.services.topics_service._call_claude", side_effect=fake_call_claude):
        # Call 1 path (done_calls = 0)
        mock_db.table.side_effect = None
        mock_db.table.return_value = MagicMock()

        def table2(name):
            m = MagicMock()
            if name == "calls":
                # first call: get call row
                m.select.return_value.eq.return_value.execute.return_value.data = [
                    {"project_id": "proj-1", "transcript": "We discussed pricing."}
                ]
            elif name == "artifacts":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            elif name == "artifact_types":
                m.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = [
                    {"prompt": project_prompt}
                ]
            return m

        mock_db.table.side_effect = table2

        # Patch done_calls query to return empty (call_number=1)
        original_side = mock_db.table.side_effect
        def table3(name):
            m = original_side(name)
            if name == "calls":
                # Second .select call (done_calls) also needs to return []
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
            return m

        # Simpler: just patch _extract_topics_impl via call_number path
        # The key check: _call_claude receives the project prompt in user content
        asyncio.run(fake_call_claude("test"))  # warm up

    # The real assertion: project_prompt appears in the prompt passed to Claude
    # We test this via the integration: patch _call_claude and check captured["prompt"]
    # Full integration test is expensive; model-level test is sufficient.
    assert True  # placeholder — real assertion in step 3 integration test
```

Actually this test is too complex for a unit test. Use a simpler approach — test `_get_topics_prompt` as a standalone helper:

Replace the above with:

```python
def test_get_topics_prompt_returns_stored_prompt():
    """_get_topics_prompt returns the project's stored prompt when it exists."""
    from backend.services.topics_service import _get_topics_prompt
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = [
            {"prompt": "STORED PROMPT"}
        ]
    result = _get_topics_prompt("proj-1", mock_db)
    assert result == "STORED PROMPT"


def test_get_topics_prompt_falls_back_to_default():
    """_get_topics_prompt returns None when no topics prompt exists in DB."""
    from backend.services.topics_service import _get_topics_prompt
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .order.return_value.limit.return_value.execute.return_value.data = []
    result = _get_topics_prompt("proj-1", mock_db)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest backend/tests/test_topics.py::test_get_topics_prompt_returns_stored_prompt backend/tests/test_topics.py::test_get_topics_prompt_falls_back_to_default -v
```

Expected: FAIL — `_get_topics_prompt` does not exist yet.

- [ ] **Step 3: Implement `_get_topics_prompt` and wire it into `_extract_topics_impl`**

In `backend/services/topics_service.py`, add after `_get_previous_topics`:

```python
def _get_topics_prompt(project_id: str, db) -> str | None:
    """Return the project's stored topics-extraction prompt, or None if not set."""
    rows = (
        db.table("artifact_types")
        .select("prompt")
        .eq("project_id", project_id)
        .eq("category", "topics")
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["prompt"] if rows else None
```

Then in `_extract_topics_impl`, replace the hardcoded prompt body with the stored one. The current Call 1 path builds:

```python
prompt = (
    f"Extract all key business topics from this call.\n\n"
    f"Return a JSON array where each element matches: {_TOPIC_SCHEMA}\n\n"
    f"Transcript:\n{transcript}\n\n"
    f"Supporting documents:\n{artifact_text or 'None'}"
)
```

Replace the entire `_extract_topics_impl` function body's prompt construction section with:

```python
async def _extract_topics_impl(call_id: str) -> dict:
    db = get_client()

    call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    call = call_row[0]
    project_id = call["project_id"]
    transcript = call["transcript"] or ""

    artifacts_rows = (
        db.table("artifacts")
        .select("content")
        .eq("call_id", call_id)
        .eq("status", "done")
        .execute()
        .data
    )
    artifact_text = "\n\n".join(r["content"] for r in artifacts_rows if r.get("content"))

    done_calls = (
        db.table("calls")
        .select("id")
        .eq("project_id", project_id)
        .eq("kanban_stage", "done")
        .execute()
        .data
    )
    call_number = len(done_calls) + 1

    # Look up project's topics prompt; fall back to hardcoded schema hint
    stored_prompt = _get_topics_prompt(project_id, db)
    base_instructions = stored_prompt or (
        f"Extract all key business topics from this call.\n\n"
        f"Return a JSON array where each element matches: {_TOPIC_SCHEMA}"
    )

    if call_number == 1:
        prompt = (
            f"{base_instructions}\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Supporting documents:\n{artifact_text or 'None'}"
        )
        topics = await _call_claude(prompt)
        return {"call_number": 1, "followed_up": [], "not_discussed": [], "new_topics": topics}

    previous = _get_previous_topics(project_id, db)
    prev_names = {t["name"] for t in previous}

    prompt = (
        f"{base_instructions}\n\n"
        f"Below are the open topics from previous calls.\n\n"
        f"Previous topics (JSON):\n{json.dumps(previous, indent=2)}\n\n"
        f"Now review the new call transcript below. For each previous topic:\n"
        f"- If it was discussed, update summary/follow_ups/decisions/status/sentiment accordingly.\n"
        f"- If it was NOT discussed, return it unchanged.\n"
        f"Also extract any brand new topics not in the previous list.\n\n"
        f"Return a JSON object with three keys: "
        f'"followed_up" (array), "not_discussed" (array), "new_topics" (array). '
        f"Each topic matches: {_TOPIC_SCHEMA}\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Supporting documents:\n{artifact_text or 'None'}"
    )
    raw = await _call_claude(prompt)

    if isinstance(raw, list):
        followed_up = [t for t in raw if t["name"] in prev_names]
        not_discussed = [t for t in previous if t["name"] not in {x["name"] for x in raw}]
        new_topics = [t for t in raw if t["name"] not in prev_names]
    else:
        followed_up = raw.get("followed_up", [])
        not_discussed = raw.get("not_discussed", [])
        new_topics = raw.get("new_topics", [])

    return {
        "call_number": call_number,
        "followed_up": followed_up,
        "not_discussed": not_discussed,
        "new_topics": new_topics,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest backend/tests/test_topics.py::test_get_topics_prompt_returns_stored_prompt backend/tests/test_topics.py::test_get_topics_prompt_falls_back_to_default -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: topics service reads prompt from artifact_types DB"
```

---

## Task 4: Frontend — add `category` to types + split Artifacts page

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/ArtifactTypeCard.tsx`
- Modify: `frontend/app/projects/[id]/artifacts/page.tsx`

### Context

`ArtifactType` needs a `category` field. The Artifacts page currently shows all types in one list. After this task:
- The top section shows `category='artifacts'` types (the current list, labelled "Artifact Types")
- A second section below shows the single `category='topics'` row (labelled "Topics Extraction Prompt") using the same `ArtifactTypeCard` — editable like any other, but no delete button (it's the seeded prompt)
- The `+ Add artifact type` button and modal stay in the artifacts section only
- The "Custom" badge in `ArtifactTypeCard` is renamed to "Artifacts"

### Steps

- [ ] **Step 1: Add `category` to `ArtifactType` in `frontend/src/types/index.ts`**

Find:
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

Replace with:
```typescript
export type ArtifactCategory = "artifacts" | "topics";

export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  category: ArtifactCategory;
  llm: LLMProvider | null;
  created_at: string;
}
```

- [ ] **Step 2: Rename "Custom" → "Artifacts" badge in `ArtifactTypeCard.tsx`**

Read `frontend/src/components/ArtifactTypeCard.tsx`. Find the badge that renders "Custom" for non-default types. It will look something like:

```tsx
<span ...>{type.is_default ? "Default" : "Custom"}</span>
```

Change `"Custom"` to `"Artifacts"`.

- [ ] **Step 3: Update `ArtifactsPage` to split the list and show topics prompt section**

Replace `frontend/app/projects/[id]/artifacts/page.tsx` content with:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { artifactTypesAPI, projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { ArtifactType, LLMProvider, Project } from "@/types";
import ArtifactTypeCard from "@/components/ArtifactTypeCard";
import AddArtifactTypeModal from "@/components/AddArtifactTypeModal";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "groq",     label: "Groq – Llama 3.3 (free)" },
  { value: "deepseek", label: "DeepSeek Chat (~free)" },
  { value: "claude",   label: "Claude Haiku" },
  { value: "openai",   label: "GPT-4o mini" },
];

export default function ArtifactsPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [savingLlm, setSavingLlm] = useState(false);
  const [llmSaveError, setLlmSaveError] = useState<string | null>(null);

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

  useEffect(() => { load(); }, [load]);

  async function handleDelete(typeId: string) {
    try {
      await artifactTypesAPI.delete(projectId, typeId);
      setTypes((prev) => prev.filter((t) => t.id !== typeId));
      logger.info("Deleted artifact type", { component: "ArtifactsPage", data: { typeId } });
    } catch (err) {
      logger.error("Failed to delete artifact type", { component: "ArtifactsPage", data: err });
    }
  }

  async function handleUpdateDefaultLlm(llm: LLMProvider) {
    if (!project) return;
    setSavingLlm(true);
    setLlmSaveError(null);
    try {
      const updated = await projectsAPI.update(projectId, { default_llm: llm });
      setProject(updated);
      logger.info("Updated project default LLM", { component: "ArtifactsPage", data: { llm } });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save";
      setLlmSaveError(msg);
      logger.error("Failed to update default LLM", { component: "ArtifactsPage", data: err });
    } finally {
      setSavingLlm(false);
    }
  }

  async function handleUpdate(typeId: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null }) {
    const updated = await artifactTypesAPI.update(projectId, typeId, data);
    setTypes((prev) => prev.map((t) => (t.id === typeId ? updated : t)));
  }

  const artifactTypes = types.filter((t) => t.category === "artifacts" || !t.category);
  const topicsPrompts = types.filter((t) => t.category === "topics");

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <h1 className="text-[18px] font-bold text-[#172b4d]">Artifact Types</h1>
        <div className="flex items-center gap-3">
          {project && (
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[#5e6c84]">Project default:</span>
                <select
                  value={project.default_llm}
                  onChange={(e) => handleUpdateDefaultLlm(e.target.value as LLMProvider)}
                  disabled={savingLlm}
                  className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] disabled:opacity-50"
                >
                  {LLM_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                {savingLlm && <span className="text-[11px] text-[#5e6c84]">Saving…</span>}
              </div>
              {llmSaveError && (
                <span className="text-[11px] text-red-600">{llmSaveError}</span>
              )}
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

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <p className="text-[13px] text-[#5e6c84]">Loading…</p>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <p className="text-[13px] text-red-600">{error}</p>
            <button onClick={load} className="text-[13px] text-[#0052cc] underline">Retry</button>
          </div>
        ) : (
          <>
            {/* ── Artifacts section ── */}
            <div className="flex flex-col gap-3 mb-8">
              {artifactTypes.length === 0 ? (
                <p className="text-[13px] text-[#5e6c84]">No artifact types yet.</p>
              ) : (
                artifactTypes.map((t) => (
                  <ArtifactTypeCard
                    key={t.id}
                    type={t}
                    projectDefaultLlm={project?.default_llm ?? "groq"}
                    onDelete={handleDelete}
                    onUpdate={handleUpdate}
                  />
                ))
              )}
            </div>

            {/* ── Topics Extraction Prompt section ── */}
            {topicsPrompts.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <h2 className="text-[13px] font-700 text-[#172b4d] font-bold">Topics Extraction Prompt</h2>
                  <span className="text-[10px] font-bold uppercase tracking-wide bg-[#e9f0ff] text-[#0052cc] px-2 py-[2px] rounded">
                    Topics
                  </span>
                  <span className="text-[11px] text-[#5e6c84]">— used by "Extract via Claude" on the Topics stage</span>
                </div>
                {topicsPrompts.map((t) => (
                  <ArtifactTypeCard
                    key={t.id}
                    type={t}
                    projectDefaultLlm={project?.default_llm ?? "groq"}
                    onDelete={() => {}} // topics prompt is not deletable
                    onUpdate={handleUpdate}
                    hideDelete
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {showModal && (
        <AddArtifactTypeModal
          projectId={projectId}
          onClose={() => setShowModal(false)}
          onCreated={(t) => setTypes((prev) => [...prev, t])}
          onImported={(ts) => setTypes((prev) => [...prev, ...ts])}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add `hideDelete` prop to `ArtifactTypeCard`**

Read `frontend/src/components/ArtifactTypeCard.tsx`. Add `hideDelete?: boolean` to its Props type and wrap the delete button render with `{!hideDelete && (...)  }`.

- [ ] **Step 5: Compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: artifacts page split, category field, rename Custom→Artifacts"
```

---

## Task 5: Backfill existing projects

Existing projects in Supabase were seeded before the topics prompt existed. They need the topics prompt row inserted.

- [ ] **Step 1: Run the following SQL in the Supabase dashboard**

```sql
-- Insert topics prompt for every project that doesn't have one yet
INSERT INTO artifact_types (project_id, name, prompt, is_default, category)
SELECT
  p.id,
  'Topics Extraction',
  E'You are an expert at extracting business topics from client call transcripts.\n\nExtract all key business topics discussed. For each topic return a JSON object matching:\n{"name":"string","summary":"string","follow_up_items":["string"],"decisions":["string"],"status":"open|in_progress|resolved","owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}\n\nFocus on: decisions made, open questions, action items, relationship dynamics, technical blockers.\nBe specific — "Pricing" not "Discussion", "API Integration Timeline" not "Technical".',
  true,
  'topics'
FROM projects p
WHERE NOT EXISTS (
  SELECT 1 FROM artifact_types a
  WHERE a.project_id = p.id AND a.category = 'topics'
);
```

Expected: rows inserted equal to number of existing projects.

- [ ] **Step 2: Commit the backfill SQL as a reference file**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] chore: backfill SQL for topics prompt on existing projects"
```

---

## Self-Review

**Spec coverage:**
- ✅ `category` column added to `artifact_types` — Task 1
- ✅ Default artifact rows seeded with `category='artifacts'` — Task 2
- ✅ Default topics prompt seeded with `category='topics'` per project — Task 2
- ✅ User-created artifact types always get `category='artifacts'` — Task 2
- ✅ `extract_topics` reads project's stored prompt — Task 3
- ✅ Fallback to hardcoded if no stored prompt — Task 3
- ✅ `ArtifactType` TypeScript type has `category` — Task 4
- ✅ "Custom" badge renamed "Artifacts" — Task 4
- ✅ Artifacts page splits into two sections — Task 4
- ✅ Topics prompt row shows "Topics" badge, no delete — Task 4
- ✅ Existing projects get backfilled — Task 5

**Placeholder scan:** None found.

**Type consistency:** `ArtifactCategory` defined in Task 4 Step 1, used in `ArtifactType`. `_get_topics_prompt` defined in Task 3 Step 3, used in `_extract_topics_impl` in same step. `hideDelete` prop added in Task 4 Step 4, consumed in Task 4 Step 3. Consistent.
