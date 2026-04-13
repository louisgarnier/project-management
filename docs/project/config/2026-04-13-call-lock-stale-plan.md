# Call Lock & Stale Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Lock/Unlock mechanism to the Done stage so calls can be explicitly finalized, with soft stale tracking when transcript or topics are edited post-generation.

**Architecture:** Three coordinated layers: (1) DB migration adds `is_locked` and `topics_stale` to `calls`, and `"stale"` to the artifact status constraint; (2) backend wires stale cascade into `PATCH /transcript` and `POST /topics`, and adds `POST /lock` + `POST /unlock` endpoints; (3) frontend adds Lock/Unlock button to Done page, read-only enforcement when locked, stale badges on ArtifactsPanel, and stale banner + re-extract on TopicsPanel.

**Tech Stack:** FastAPI + Supabase (Postgres), Python unittest.mock, Next.js 15 App Router, TypeScript, inline styles.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Create | `backend/database/migrations/009_call_lock_stale.sql` | New columns + expanded status constraint |
| Modify | `backend/routers/calls.py` | `update_transcript` cascades stale; new lock/unlock endpoints |
| Modify | `backend/routers/topics.py` | `save` cascades artifacts stale when call is done |
| Modify | `backend/tests/test_calls.py` | Tests for stale cascade + lock/unlock |
| Modify | `frontend/src/types/index.ts` | Add `is_locked`, `topics_stale` to `Call` |
| Modify | `frontend/src/api/client.ts` | Add `callsAPI.lock`, `callsAPI.unlock` |
| Modify | `frontend/src/components/ArtifactsPanel.tsx` | Stale badge + Regenerate button per artifact |
| Modify | `frontend/src/components/TopicsPanel.tsx` | Stale banner + Re-extract button |
| Modify | `frontend/src/components/TranscriptPanel.tsx` | Read-only when locked |
| Modify | `frontend/app/projects/[id]/calls/[call_id]/page.tsx` | Lock/Unlock button on Done page; pass `call` prop to panels |

---

## Task 1: DB migration

**Files:**
- Create: `backend/database/migrations/009_call_lock_stale.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- 009_call_lock_stale.sql
-- Add lock and stale tracking to calls table.
-- Expand artifact status to include 'stale'.
-- Run once in Supabase SQL editor.

ALTER TABLE calls ADD COLUMN IF NOT EXISTS is_locked boolean NOT NULL DEFAULT false;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS topics_stale boolean NOT NULL DEFAULT false;

-- Expand the artifact status constraint to allow 'stale'
ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_status_check;
ALTER TABLE artifacts ADD CONSTRAINT artifacts_status_check
  CHECK (status IN ('pending', 'generating', 'done', 'error', 'stale'));
```

- [ ] **Step 2: Run migration in Supabase SQL editor**

Paste and execute the SQL above. Verify no errors.

- [ ] **Step 3: Commit the migration file**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-6] chore: migration 009 — call lock/stale columns, artifact stale status"
```

---

## Task 2: Backend — lock/unlock endpoints + stale cascade

**Files:**
- Modify: `backend/routers/calls.py`
- Modify: `backend/routers/topics.py`
- Test: `backend/tests/test_calls.py`

### Context

`PATCH /api/calls/{call_id}/transcript` (the `update_transcript` function) is called when editing transcript on a call that is past the transcript stage. When the call is at `"done"`, this edit should cascade: set `topics_stale=True` and flip all artifacts for that call to `status="stale"`.

`POST /api/calls/{call_id}/topics` (the `save` endpoint in topics router) saves topic updates. When the call is at `"done"`, saving topics should cascade: flip all artifacts for that call to `status="stale"`.

Two new endpoints:
- `POST /api/calls/{call_id}/lock` → sets `is_locked=True`
- `POST /api/calls/{call_id}/unlock` → sets `is_locked=False`

- [ ] **Step 1: Write failing tests**

Read `backend/tests/test_calls.py` to understand the `_mock_client` helper and `MOCK_CALL` fixture, then add these tests:

```python
def test_update_transcript_on_done_call_sets_stale():
    """PATCH /transcript on a done call must set topics_stale=True and mark artifacts stale."""
    mc = _mock_client()

    call_select = MagicMock()
    call_select.data = [{"kanban_stage": "done"}]

    artifact_select = MagicMock()
    artifact_select.data = [{"id": "art-1"}, {"id": "art-2"}]

    update_call = MagicMock()
    update_call.data = [{**MOCK_CALL, "kanban_stage": "done", "topics_stale": True}]

    call_count = 0

    def table_side(name):
        m = MagicMock()
        if name == "calls":
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                m.select.return_value.eq.return_value.execute.return_value = call_select
            else:
                m.update.return_value.eq.return_value.execute.return_value = update_call
        elif name == "artifacts":
            m.select.return_value.eq.return_value.execute.return_value = artifact_select
            m.update.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
        return m

    mc.table.side_effect = table_side

    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.patch(
            f"/api/calls/{CALL_ID}/transcript",
            json={"transcript": "Updated transcript"},
        )
    assert r.status_code == 200
    assert r.json()["topics_stale"] is True


def test_lock_call():
    mc = _mock_client()
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{**MOCK_CALL, "is_locked": True}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(f"/api/calls/{CALL_ID}/lock")
    assert r.status_code == 200
    assert r.json()["is_locked"] is True


def test_unlock_call():
    mc = _mock_client()
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{**MOCK_CALL, "is_locked": False}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(f"/api/calls/{CALL_ID}/unlock")
    assert r.status_code == 200
    assert r.json()["is_locked"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/test_calls.py::test_update_transcript_on_done_call_sets_stale backend/tests/test_calls.py::test_lock_call backend/tests/test_calls.py::test_unlock_call -v
```

Expected: FAIL — endpoints don't exist yet.

- [ ] **Step 3: Update `update_transcript` in `backend/routers/calls.py`**

Read `backend/routers/calls.py`. Find `update_transcript` (the `PATCH /calls/{call_id}/transcript` handler). Replace the full function body:

```python
@router.patch("/calls/{call_id}/transcript")
def update_transcript(call_id: str, payload: TranscriptUpdate):
    client = get_client()
    db_logger.info(f"🗄️ [DB] Fetching call for transcript update: {call_id}")
    result = client.table("calls").select("kanban_stage").eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")

    current_stage = result.data[0]["kanban_stage"]
    if current_stage == "transcript":
        raise HTTPException(
            status_code=409,
            detail="Call is at transcript stage — use POST /transcript to save and advance",
        )

    update_data: dict = {"transcript": payload.transcript}

    # When editing transcript on a done call, mark topics and artifacts as stale
    if current_stage == "done":
        update_data["topics_stale"] = True
        artifacts = (
            client.table("artifacts")
            .select("id")
            .eq("call_id", call_id)
            .execute()
            .data
        )
        artifact_ids = [a["id"] for a in artifacts]
        if artifact_ids:
            client.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
            db_logger.info(f"⚠️ [DB] Marked {len(artifact_ids)} artifacts stale: {call_id}")

    db_logger.info(f"🗄️ [DB] Updating transcript for call: {call_id}")
    update_result = (
        client.table("calls")
        .update(update_data)
        .eq("id", call_id)
        .execute()
    )
    db_logger.info(f"✅ [DB] Transcript updated: {call_id}")
    return update_result.data[0]
```

- [ ] **Step 4: Add lock and unlock endpoints to `backend/routers/calls.py`**

Append after `update_transcript`:

```python
@router.post("/calls/{call_id}/lock")
def lock_call(call_id: str):
    client = get_client()
    result = client.table("calls").update({"is_locked": True}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"🔒 [DB] Call locked: {call_id}")
    return result.data[0]


@router.post("/calls/{call_id}/unlock")
def unlock_call(call_id: str):
    client = get_client()
    result = client.table("calls").update({"is_locked": False}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"🔓 [DB] Call unlocked: {call_id}")
    return result.data[0]
```

- [ ] **Step 5: Update topics save in `backend/routers/topics.py`**

Read `backend/routers/topics.py`. Find the `save` endpoint (`POST /calls/{call_id}/topics`). After the existing `await save_topics(call_id, topics)` call, add the artifacts stale cascade:

```python
@router.post("/calls/{call_id}/topics")
async def save(call_id: str, topics: list[TopicUpdate]):
    logger.info(f"📥 [Topics] Save requested: call={call_id}, count={len(topics)}")
    try:
        result = await save_topics(call_id, topics)

        # When saving topics on a done call, mark artifacts as stale
        db = get_client()
        call_row = db.table("calls").select("kanban_stage").eq("id", call_id).execute().data
        if call_row and call_row[0]["kanban_stage"] == "done":
            artifacts = db.table("artifacts").select("id").eq("call_id", call_id).execute().data
            artifact_ids = [a["id"] for a in artifacts]
            if artifact_ids:
                db.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
                logger.info(f"⚠️ [Topics] Marked {len(artifact_ids)} artifacts stale after topic save: {call_id}")

        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save failed: {e}")
        raise HTTPException(status_code=500, detail="Topic save failed")
```

- [ ] **Step 6: Run failing tests — they should now pass**

```bash
python3 -m pytest backend/tests/test_calls.py::test_update_transcript_on_done_call_sets_stale backend/tests/test_calls.py::test_lock_call backend/tests/test_calls.py::test_unlock_call -v
```

Expected: PASS.

- [ ] **Step 7: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: all existing tests pass (94+ pass, 1 pre-existing failure). Fix any new failures before continuing.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: lock/unlock endpoints + stale cascade on transcript and topics edit"
```

---

## Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add fields to `Call` interface in `frontend/src/types/index.ts`**

Read the file. Find the `Call` interface. Add two fields after `created_at`:

```typescript
export interface Call {
  id: string;
  project_id: string;
  title: string;
  transcript: string | null;
  transcript_source: string | null;
  kanban_stage: KanbanStage;
  is_locked: boolean;
  topics_stale: boolean;
  created_at: string;
}
```

- [ ] **Step 2: Add `lock` and `unlock` to `callsAPI` in `frontend/src/api/client.ts`**

Read the file. Find `callsAPI`. Add after `updateTranscript`:

```typescript
  lock: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/lock`, { method: "POST" }),
  unlock: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/unlock`, { method: "POST" }),
```

- [ ] **Step 3: TypeScript compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors. Fix any type errors before continuing.

- [ ] **Step 4: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-6] feat: add is_locked, topics_stale to Call type + lock/unlock API methods"
```

---

## Task 4: ArtifactsPanel — stale badge + regenerate button

**Files:**
- Modify: `frontend/src/components/ArtifactsPanel.tsx`

### Context

`ArtifactsPanel` is a collapsible read-only panel used on the Done page and historical views. It receives `callId` and `projectId`. We need to add a `call` prop so it knows `is_locked`. When `!call.is_locked`, show a "Regenerate" button on each artifact. Stale artifacts (`status === "stale"`) get an orange badge.

Regeneration flow: PATCH the artifact to `status="pending"` via `artifactsAPI.update`, then open the SSE stream (`/api/sse/api/calls/{callId}/artifacts/stream`) to receive status updates. This is the same SSE pattern already used in `ArtifactsStage.tsx` — replicate it here.

The `artifactsAPI.update` signature (from `frontend/src/api/client.ts`):
```typescript
update: (artifactId: string, data: Partial<Artifact>) => proxyFetch<Artifact>(...)
```

- [ ] **Step 1: Read `frontend/src/components/ArtifactsPanel.tsx` and `frontend/src/api/client.ts`**

Understand the current structure before editing.

- [ ] **Step 2: Rewrite `frontend/src/components/ArtifactsPanel.tsx`**

Replace the full file content:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactTypesAPI, artifactsAPI } from "@/api/client";
import type { Artifact, ArtifactType, Call } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
  call?: Call; // when provided, enables regeneration (if not locked)
};

export default function ArtifactsPanel({ callId, projectId, defaultOpen = false, call }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const [arts, artTypes] = await Promise.all([
        artifactsAPI.list(callId),
        artifactTypesAPI.list(projectId),
      ]);
      setArtifacts(arts);
      setTypes(artTypes);
    } finally {
      setLoading(false);
    }
  }, [open, callId, projectId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { return () => { streamAbortRef.current?.abort(); }; }, []);

  const typesById = Object.fromEntries(types.map((t) => [t.id, t]));
  const canRegenerate = call && !call.is_locked;

  async function handleRegenerate(artifact: Artifact) {
    // Reset to pending then stream
    const updated = await artifactsAPI.update(artifact.id, { status: "pending" });
    setArtifacts((prev) => prev.map((a) => (a.id === artifact.id ? updated : a)));
    setStreaming(true);

    const controller = new AbortController();
    streamAbortRef.current = controller;

    try {
      const response = await fetch(`/api/sse/api/calls/${callId}/artifacts/stream`, {
        signal: controller.signal,
      });
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "complete") break;
            setArtifacts((prev) =>
              prev.map((a) => {
                if (a.id !== event.artifact_id) return a;
                if (event.type === "status") return { ...a, status: event.status };
                if (event.type === "done") return { ...a, status: "done", content: event.content ?? null };
                if (event.type === "error") return { ...a, status: "error", error_message: event.message ?? null };
                return a;
              })
            );
          } catch { /* malformed line */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        console.error("SSE error", err);
      }
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        <span style={{ fontSize: 12, fontWeight: 700, color: "#172b4d" }}>
          Artifacts {artifacts.length > 0 && !loading ? `(${artifacts.length})` : ""}
        </span>
        <span style={{ fontSize: 10, color: "#97a0af" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #f4f5f7", padding: "10px 14px" }}>
          {loading ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading…</p>
          ) : artifacts.length === 0 ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>No artifacts generated for this call.</p>
          ) : (
            artifacts.map((a) => (
              <ArtifactRow
                key={a.id}
                artifact={a}
                name={typesById[a.artifact_type_id]?.name ?? "Artifact"}
                canRegenerate={!!canRegenerate && !streaming}
                onRegenerate={() => handleRegenerate(a)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ArtifactRow({ artifact, name, canRegenerate, onRegenerate }: {
  artifact: Artifact;
  name: string;
  canRegenerate: boolean;
  onRegenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const isStale = artifact.status === "stale";
  const isPending = artifact.status === "pending" || artifact.status === "generating";

  return (
    <div style={{ borderBottom: "1px solid #f4f5f7", paddingBottom: 8, marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => setExpanded((e) => !e)}
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0,
            fontSize: 12, fontWeight: 600, color: "#172b4d", display: "flex", alignItems: "center", gap: 6, flex: 1 }}
        >
          <span>{expanded ? "▼" : "▶"}</span>
          <span>{name}</span>
        </button>
        {isStale && (
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            background: "#fff4e6", color: "#974f0c", padding: "2px 6px", borderRadius: 3 }}>
            stale
          </span>
        )}
        {isPending && (
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            background: "#e9f0ff", color: "#0052cc", padding: "2px 6px", borderRadius: 3 }}>
            {artifact.status}
          </span>
        )}
        {canRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={isPending}
            style={{ fontSize: 10, color: "#0052cc", background: "none",
              border: "1px solid #b3c6e8", borderRadius: 4, padding: "2px 8px",
              cursor: isPending ? "not-allowed" : "pointer", opacity: isPending ? 0.5 : 1 }}
          >
            ↻ Regenerate
          </button>
        )}
      </div>
      {expanded && artifact.content && (
        <pre style={{ marginTop: 8, fontSize: 11, color: "#344563", whiteSpace: "pre-wrap",
          background: "#f4f5f7", borderRadius: 4, padding: "8px 10px", lineHeight: 1.6 }}>
          {artifact.content}
        </pre>
      )}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-6] feat: ArtifactsPanel stale badge + regenerate button"
```

---

## Task 5: TopicsPanel — stale banner + re-extract + TranscriptPanel read-only

**Files:**
- Modify: `frontend/src/components/TopicsPanel.tsx`
- Modify: `frontend/src/components/TranscriptPanel.tsx`

### Context

`TopicsPanel` needs a `call` prop. When `call.topics_stale && !call.is_locked`, show an orange banner: "Transcript was updated — topics may be out of date." with a "Re-extract" button and a "Dismiss" button.

"Re-extract" calls `topicsAPI.extract(callId)` and saves the result via `topicsAPI.save`. After saving, call `callsAPI`'s PATCH to clear `topics_stale` — but we don't have a dedicated endpoint for that. Instead, re-extract + save will naturally update the topics. To clear `topics_stale`, add a new PATCH call: `PATCH /api/calls/{callId}` with `{ topics_stale: false }`. Actually, the simplest approach: after saving topics successfully, call `topicsAPI.validate` which already exists and advances the stage. But we're already at done...

Simplest: add `callsAPI.clearTopicsStale(callId)` that calls a new `PATCH /api/calls/{call_id}/topics_stale` endpoint setting it to false. OR reuse the existing general PATCH if one exists.

Looking at `backend/routers/calls.py`, there is no general PATCH. The simplest addition: `DELETE /api/calls/{call_id}/topics_stale` clears the flag. Or add it to the lock endpoint logic.

Actually simplest: the "Re-extract" button calls `topicsAPI.extract` → shows results → user reviews in TopicsPanel → clicks "Save" → `topicsAPI.save` → then call a new `callsAPI.clearTopicsStale` endpoint.

For the plan, I'll use a new dedicated endpoint `POST /api/calls/{call_id}/clear_stale` that sets `topics_stale=False` (no artifact impact).

`TranscriptPanel` needs: when `call.is_locked`, make the textarea disabled and hide the Save button.

- [ ] **Step 1: Add `clear_stale` endpoint to `backend/routers/calls.py`**

Read the file, then append:

```python
@router.post("/calls/{call_id}/clear_stale")
def clear_topics_stale(call_id: str):
    """Clear the topics_stale flag after topics have been re-reviewed."""
    client = get_client()
    result = client.table("calls").update({"topics_stale": False}).eq("id", call_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Call not found")
    db_logger.info(f"✅ [DB] topics_stale cleared: {call_id}")
    return result.data[0]
```

- [ ] **Step 2: Add `clearTopicsStale` to `frontend/src/api/client.ts`**

In `callsAPI`, add after `unlock`:

```typescript
  clearTopicsStale: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/clear_stale`, { method: "POST" }),
```

- [ ] **Step 3: Update `TopicsPanel` props and add stale banner**

Read `frontend/src/components/TopicsPanel.tsx`. Add `call?: Call` to the `Props` type and add the stale banner + re-extract flow.

Replace the `Props` type and component signature:

```typescript
type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
  call?: Call; // when provided, enables stale banner and re-extract
};
```

Add import for `callsAPI` and `ExtractionResult` at the top:

```typescript
import { callsAPI, topicsAPI } from "@/api/client";
import type { TopicData, Call, ExtractionResult } from "@/types";
```

Add state inside the component (after existing state):

```typescript
const [reExtracting, setReExtracting] = useState(false);
const [reExtractError, setReExtractError] = useState<string | null>(null);
```

Add the `handleReExtract` function inside the component:

```typescript
async function handleReExtract() {
  setReExtracting(true);
  setReExtractError(null);
  try {
    const result: ExtractionResult = await topicsAPI.extract(callId);
    const allTopics = [
      ...result.followed_up,
      ...result.not_discussed,
      ...result.new_topics,
    ];
    await topicsAPI.save(callId, allTopics.map((t) => ({
      ...t,
      topic_id: t.topic_id ?? null,
      disposition: null,
    })));
    await callsAPI.clearTopicsStale(callId);
    await load();
  } catch (err) {
    setReExtractError(err instanceof Error ? err.message : "Re-extraction failed");
  } finally {
    setReExtracting(false);
  }
}

async function handleDismissStale() {
  try {
    await callsAPI.clearTopicsStale(callId);
    // parent will re-render call with topics_stale=false once it refreshes
  } catch { /* ignore */ }
}
```

Add the stale banner inside the `{open && (...)}` block, before the loading/topics content:

```tsx
{call?.topics_stale && !call.is_locked && (
  <div style={{ margin: "0 14px 10px", background: "#fff4e6", border: "1px solid #ffe0a0",
    borderRadius: 6, padding: "8px 12px", fontSize: 11, color: "#974f0c" }}>
    <div style={{ fontWeight: 700, marginBottom: 4 }}>⚠ Transcript was updated — topics may be out of date</div>
    {reExtractError && <div style={{ color: "#ae2a19", marginBottom: 4 }}>{reExtractError}</div>}
    <div style={{ display: "flex", gap: 8 }}>
      <button
        onClick={handleReExtract}
        disabled={reExtracting}
        style={{ fontSize: 10, fontWeight: 600, background: "#974f0c", color: "white",
          border: "none", padding: "3px 10px", borderRadius: 4,
          cursor: reExtracting ? "not-allowed" : "pointer", opacity: reExtracting ? 0.6 : 1 }}
      >
        {reExtracting ? "Re-extracting…" : "Re-extract topics"}
      </button>
      <button
        onClick={handleDismissStale}
        style={{ fontSize: 10, color: "#974f0c", background: "none", border: "none",
          cursor: "pointer", textDecoration: "underline" }}
      >
        Dismiss
      </button>
    </div>
  </div>
)}
```

Also update the `TopicRow` inside `TopicsPanel` — when `call?.is_locked`, hide the ✎ edit button. Find `TopicRow` and update the edit button:

```tsx
{!callIsLocked && (
  <button onClick={() => setEditing(true)}
    style={{ fontSize: 11, color: "#97a0af", background: "none", border: "none",
      cursor: "pointer", padding: 0 }} title="Edit">
    ✎
  </button>
)}
```

Pass `callIsLocked` as a prop to `TopicRow`:

```typescript
function TopicRow({ topic, callId, onSaved, callIsLocked }: {
  topic: TopicData; callId: string; onSaved: () => void; callIsLocked: boolean;
})
```

And in the parent map: `<TopicRow ... callIsLocked={!!(call?.is_locked)} />`

Also hide "+ Add topic" button when locked:

```tsx
{!call?.is_locked && (
  <button onClick={() => setShowAdd(true)} ...>
    + Add topic
  </button>
)}
```

- [ ] **Step 4: Update `TranscriptPanel` to be read-only when locked**

Read `frontend/src/components/TranscriptPanel.tsx`. The `call` prop already exists. Make these changes:

1. Make textarea disabled when locked:
```tsx
<textarea
  ...
  disabled={call.is_locked}
  style={{ minHeight: "280px", opacity: call.is_locked ? 0.7 : 1 }}
/>
```

2. Hide the Save button when locked (show a locked indicator instead):
```tsx
{call.is_locked ? (
  <span style={{ fontSize: 11, color: "#97a0af" }}>🔒 Locked — unlock to edit</span>
) : (
  <button onClick={handleSave} disabled={!isDirty || saving || !text.trim()} ...>
    {saving ? "Saving…" : "Save changes"}
  </button>
)}
```

- [ ] **Step 5: TypeScript compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors. Fix any type errors.

- [ ] **Step 6: Run backend tests**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: TopicsPanel stale banner + re-extract; TranscriptPanel read-only when locked"
```

---

## Task 6: Done page — Lock/Unlock button + pass `call` prop to panels

**Files:**
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

### Context

The Done page is the `call.kanban_stage === "done"` block inside `page.tsx`. It currently renders:
- A green "Call complete" banner
- `<TopicsPanel callId={callId} projectId={projectId} defaultOpen />`
- `<ArtifactsPanel callId={callId} projectId={projectId} />`
- `<TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />`
- `<ContextFiles call={call} readonly />`

Changes:
1. Add Lock/Unlock button in the Done banner area
2. Pass `call={call}` to `ArtifactsPanel` and `TopicsPanel`
3. When locked, pass `readonly` to `ContextFiles` (already done)

The lock/unlock button calls `callsAPI.lock(callId)` or `callsAPI.unlock(callId)`, then calls `setCall(updated)` with the returned call.

Also: pass `call={call}` to `TopicsPanel` and `ArtifactsPanel` in the `viewStage === "done"` historical view handler as well.

- [ ] **Step 1: Update the `done` stage block in `page.tsx`**

Read `frontend/app/projects/[id]/calls/[call_id]/page.tsx`. Find the `{call.kanban_stage === "done" && (` block. Replace it:

```tsx
        {call.kanban_stage === "done" && (
          <>
            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8,
              padding: "12px 16px", marginBottom: 16, fontSize: 13, color: "#15803d",
              display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 600 }}>✓ Call complete — all topics validated and artifacts saved.</span>
              {call.is_locked ? (
                <button
                  onClick={async () => { const updated = await callsAPI.unlock(callId); setCall(updated); }}
                  style={{ fontSize: 12, fontWeight: 600, background: "white", color: "#5e6c84",
                    border: "1px solid #dfe1e6", borderRadius: 6, padding: "5px 14px", cursor: "pointer" }}
                >
                  🔓 Unlock
                </button>
              ) : (
                <button
                  onClick={async () => { const updated = await callsAPI.lock(callId); setCall(updated); }}
                  style={{ fontSize: 12, fontWeight: 600, background: "#172b4d", color: "white",
                    border: "none", borderRadius: 6, padding: "5px 14px", cursor: "pointer" }}
                >
                  🔒 Lock Call
                </button>
              )}
            </div>
            {call.is_locked && (
              <div style={{ fontSize: 11, color: "#97a0af", background: "#f4f5f7",
                borderRadius: 6, padding: "6px 12px", marginBottom: 12 }}>
                🔒 This call is locked. Unlock to edit transcript, topics, or regenerate artifacts.
              </div>
            )}
            <TopicsPanel callId={callId} projectId={projectId} defaultOpen call={call} />
            <ArtifactsPanel callId={callId} projectId={projectId} call={call} />
            {call.transcript && (
              <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
            )}
            <ContextFiles call={call} readonly />
          </>
        )}
```

- [ ] **Step 2: Add `callsAPI` import if not already present**

Check the imports at the top of `page.tsx`. `callsAPI` should already be imported. If not, add it:

```typescript
import { artifactsAPI, callsAPI } from "@/api/client";
```

- [ ] **Step 3: Update `viewStage === "done"` historical view to pass `call` prop**

Find the `if (viewStage === "done")` block. Update `TopicsPanel` and `ArtifactsPanel` to pass `call={call}`:

```tsx
          <TopicsPanel callId={callId} projectId={projectId} defaultOpen call={call} />
          <ArtifactsPanel callId={callId} projectId={projectId} call={call} />
```

- [ ] **Step 4: TypeScript compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-6] feat: Lock/Unlock button on Done page; pass call prop to panels"
```

---

## Self-Review

**Spec coverage:**
- ✅ `is_locked` + `topics_stale` in DB — Task 1
- ✅ Lock/Unlock endpoints — Task 2
- ✅ Stale cascade on transcript edit (done call) — Task 2
- ✅ Stale cascade on topic save (done call) — Task 2
- ✅ Call type updated — Task 3
- ✅ API client lock/unlock — Task 3
- ✅ ArtifactsPanel stale badge + Regenerate button — Task 4
- ✅ TopicsPanel stale banner + Re-extract + Dismiss — Task 5
- ✅ TranscriptPanel read-only when locked — Task 5
- ✅ Lock/Unlock button on Done page — Task 6
- ✅ Locked info banner — Task 6
- ✅ `call` prop passed to ArtifactsPanel and TopicsPanel on done view — Task 6

**Placeholder scan:** None found.

**Type consistency:**
- `call?: Call` prop on `ArtifactsPanel` — defined Task 4, used Task 6. Optional so existing call sites without `call` prop still compile.
- `call?: Call` prop on `TopicsPanel` — defined Task 5, used Task 6. Optional so existing call sites still compile.
- `callsAPI.lock`, `callsAPI.unlock`, `callsAPI.clearTopicsStale` — defined Task 3 + Task 5, used in Task 5 and Task 6. Consistent.
- `TopicRow` gains `callIsLocked: boolean` prop — defined and used in Task 5 only. Consistent.
