# Project Topic Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single LLM-driven `project_topics` stage with two stages — `project_matching` (manual topic linking) and `project_updates` (per-match LLM merge review) — giving users full control over which call topics map to which project topics before any LLM runs.

**Architecture:** Add a `pending_topics JSONB` column to `calls` to bridge the gap between call topic extraction and manual matching; add a `topic_match_groups` table to persist the user's linking decisions (refresh-safe); replace `aggregate_topics` LLM logic with a simple "save to pending + advance stage" for Call 2+; add a new parallel-per-group LLM merge step. Call 1 auto-advances past both new stages directly to `artifacts` (unchanged).

**Tech Stack:** FastAPI, Supabase (PostgreSQL), Next.js 14, TypeScript, asyncio for parallel LLM calls.

---

## File Map

**New files:**
- `backend/database/migrations/014_project_matching_stages.sql` — DB schema changes
- `frontend/src/components/ProjectMatchingStage.tsx` — manual matching UI
- `frontend/src/components/ProjectUpdatesStage.tsx` — LLM merge review UI

**Modified files:**
- `backend/services/topics_service.py` — aggregate_topics stripped of LLM; new save_match_groups, run_merge_preview, validate_project_updates
- `backend/routers/topics.py` — new endpoints for match groups and merge preview
- `frontend/src/types/index.ts` — KanbanStage, new MatchGroup type
- `frontend/src/components/KanbanBoard.tsx` — new STAGES / STAGE_ORDER
- `frontend/src/api/client.ts` — new API methods
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — wire new stages
- `frontend/app/projects/[id]/board/page.tsx` — STAGE_ORDER if referenced

---

## Task 1: DB Migration

**Files:**
- Create: `backend/database/migrations/014_project_matching_stages.sql`

- [ ] **Step 1: Write migration SQL**

```sql
-- 014_project_matching_stages.sql
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. Extend kanban_stage CHECK constraint to include new stages
ALTER TABLE public.calls DROP CONSTRAINT IF EXISTS calls_kanban_stage_check;
ALTER TABLE public.calls ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN ('transcript','call_topics','project_matching','project_updates','artifacts','done'));

-- 2. Migrate existing project_topics rows → project_matching
--    (they haven't been matched yet so they belong at the matching step)
UPDATE public.calls SET kanban_stage = 'project_matching'
  WHERE kanban_stage = 'project_topics';

-- 3. Add pending_topics column (stores validated call topics between stages)
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS
  pending_topics JSONB;

-- 4. Create topic_match_groups table
CREATE TABLE IF NOT EXISTS public.topic_match_groups (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id          UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
  project_topic_id UUID REFERENCES public.topics(id) ON DELETE SET NULL,
  call_topic_names TEXT[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_match_groups_call_id
  ON public.topic_match_groups(call_id);
```

- [ ] **Step 2: Run in Supabase Dashboard SQL Editor — verify no errors**

- [ ] **Step 3: Verify in Supabase table editor**
  - `calls` table has `pending_topics` column and updated CHECK constraint
  - `topic_match_groups` table exists with correct columns
  - Any calls previously in `project_topics` are now in `project_matching`

---

## Task 2: Backend — Update Topics Service

**Files:**
- Modify: `backend/services/topics_service.py`

### 2a: Strip LLM logic from `aggregate_topics` (Call 2+ path)

- [ ] **Step 1: Replace the Call 2+ LLM block in `aggregate_topics`**

Find the section starting at `# Call 2+: LLM matching using stored "Project Topics Merge" prompt` and replace everything from there to the end of the function with:

```python
    # Call 2+: save pending topics and advance to project_matching for manual matching
    db.table("calls").update({
        "pending_topics": call_topics,
        "kanban_stage": "project_matching",
    }).eq("id", call_id).execute()
    logger.info(
        f"✅ [Topics] Step-2 saved {len(call_topics)} pending topics → project_matching"
    )
    return {"advanced_to": "project_matching", "call_number": call_number}
```

The complete updated `aggregate_topics` return type is now `{"auto_advanced": True}` for Call 1 or `{"advanced_to": "project_matching"}` for Call 2+. The old `followed_up / not_discussed / new_topics` response shape is gone.

### 2b: Add `get_pending_topics`

- [ ] **Step 2: Add function after `aggregate_topics`**

```python
async def get_pending_topics(call_id: str) -> list[dict]:
    """Return the validated call topics stored between call_topics and project_matching stages."""
    db = get_client()
    row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
    if not row:
        raise ValueError(f"Call {call_id} not found")
    return row[0].get("pending_topics") or []
```

### 2c: Add `save_match_groups`

- [ ] **Step 3: Add function**

```python
async def save_match_groups(call_id: str, groups: list[dict]) -> dict:
    """
    Persist match groups and advance to project_updates.

    groups: [{"project_topic_id": "uuid" | None, "call_topic_names": ["name1", ...]}]
    """
    db = get_client()

    # Delete previous groups for this call (idempotent save)
    db.table("topic_match_groups").delete().eq("call_id", call_id).execute()

    for g in groups:
        db.table("topic_match_groups").insert({
            "call_id": call_id,
            "project_topic_id": g.get("project_topic_id"),
            "call_topic_names": g.get("call_topic_names", []),
        }).execute()

    db.table("calls").update({"kanban_stage": "project_updates"}).eq("id", call_id).execute()
    logger.info(f"✅ [Topics] Saved {len(groups)} match groups → project_updates")
    return {"saved": len(groups)}
```

### 2d: Add `run_merge_preview`

- [ ] **Step 4: Add function**

```python
_MERGE_SYSTEM = (
    "You are an expert at merging client call topic records. "
    "Return ONLY valid JSON matching the schema given. No markdown, no explanation."
)

async def run_merge_preview(call_id: str) -> list[dict]:
    """
    For each match group:
    - matched (project_topic_id set): run LLM to merge existing topic + call topics → updated recap
    - new (project_topic_id None): return call topics as-is, topic_id=None

    Returns a list of topic dicts ready for ProjectUpdatesStage review.
    Each item has all TopicData fields plus topic_id (existing UUID or None).
    """
    db = get_client()

    call_row = db.table("calls").select("project_id, pending_topics").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]
    pending: list[dict] = call_row[0].get("pending_topics") or []

    groups = (
        db.table("topic_match_groups")
        .select("project_topic_id, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )

    # Build lookup: call topic name → topic dict
    pending_by_name = {t["name"].lower().strip(): t for t in pending}

    # Load previous project topics for context
    previous = _get_previous_topics(project_id, db)
    prev_by_id = {t["topic_id"]: t for t in previous}

    # Get LLM config
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db, category="project_topics")
    if stored_llm is None:
        proj_rows = db.table("projects").select("default_llm").eq("id", project_id).execute().data
        stored_llm = proj_rows[0].get("default_llm") if proj_rows else "groq"
    llm = stored_llm or "groq"

    merge_instructions = stored_prompt or (
        "You are merging an existing project topic record with one or more new call topics that match it. "
        "Produce an updated topic that synthesises the history with the latest call information. "
        "Keep the most important follow-up items (max 5). Update status, sentiment, and owner to reflect current state."
    )

    async def merge_one(group: dict) -> dict:
        ptid = group.get("project_topic_id")
        call_names = group.get("call_topic_names", [])
        call_matches = [pending_by_name[n.lower().strip()] for n in call_names if n.lower().strip() in pending_by_name]

        if ptid is None:
            # New topic — return first call topic as-is (or merged if multiple)
            if not call_matches:
                return {}
            base = call_matches[0]
            return {**base, "topic_id": None}

        existing = prev_by_id.get(ptid)
        if not existing:
            # Existing topic not found — treat as new
            base = call_matches[0] if call_matches else {}
            return {**base, "topic_id": ptid}

        if not call_matches:
            # No call topics matched — return existing unchanged (not discussed)
            return {**existing, "topic_id": ptid}

        # Run LLM merge
        prompt = (
            f"{merge_instructions}\n\n"
            f"Existing project topic:\n{json.dumps(existing, indent=2)}\n\n"
            f"New call topic(s) matching this:\n{json.dumps(call_matches, indent=2)}\n\n"
            f"Return a single merged topic JSON:\n{_TOPIC_SCHEMA}"
        )
        merged = await _call_llm(prompt, llm)
        if isinstance(merged, list):
            merged = merged[0] if merged else {}
        return {**merged, "topic_id": ptid}

    results = await asyncio.gather(*[merge_one(g) for g in groups])
    return [r for r in results if r]
```

### 2e: Add `validate_project_updates`

- [ ] **Step 5: Add function**

```python
async def validate_project_updates(call_id: str, topics: list[dict]) -> dict:
    """
    Save merged/reviewed topics and advance to artifacts.
    - topic_id set   → update existing topic (topic_update record)
    - topic_id None  → create new topic
    Clears pending_topics and topic_match_groups for this call.
    """
    db = get_client()

    topic_updates = [
        TopicUpdate(**{
            **t,
            "topic_id": t.get("topic_id"),
            "disposition": None,
        })
        for t in topics
    ]
    await save_topics(call_id, topic_updates)

    # Clean up transient data
    db.table("topic_match_groups").delete().eq("call_id", call_id).execute()
    db.table("calls").update({
        "pending_topics": None,
        "kanban_stage": "artifacts",
    }).eq("id", call_id).execute()

    logger.info(f"✅ [Topics] project_updates validated → artifacts: {call_id}")
    return {"status": "ok"}
```

- [ ] **Step 6: Restart backend and verify no import/syntax errors**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m backend.main 2>&1 | head -20
```

Expected: server starts with no errors.

---

## Task 3: Backend — New Router Endpoints

**Files:**
- Modify: `backend/routers/topics.py`

- [ ] **Step 1: Add imports at the top of the file**

Add to the existing import from topics_service:
```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_call_topics, extract_call_topics, aggregate_topics,
    get_pending_topics, save_match_groups, run_merge_preview, validate_project_updates,
    TopicUpdate,
)
```

- [ ] **Step 2: Update the `aggregate` endpoint to handle new response shape**

The endpoint at `POST /calls/{call_id}/topics/aggregate` currently checks for `result.get("auto_advanced")` and returns early. Update it to also handle the new `advanced_to` response:

```python
@router.post("/calls/{call_id}/topics/aggregate")
async def aggregate(call_id: str, payload: AggregatePayload):
    """Step 2: save pending call topics → advance to project_matching (or auto-advance Call 1)."""
    logger.info(
        f"📥 [Topics] Step-2 aggregate requested: call={call_id}, "
        f"input_topics={len(payload.topics)}"
    )
    try:
        result = await aggregate_topics(call_id, payload.topics)
        if result.get("auto_advanced"):
            logger.info(f"✅ [Topics] Auto-advanced Call 1: {call_id}")
        else:
            logger.info(f"✅ [Topics] Saved pending topics → project_matching: {call_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OpenAIStatusError as e:
        if e.status_code in (413, 429) or "rate_limit" in str(e).lower():
            logger.warning(f"⚠️ [Topics] LLM rate limit on Step-2: {e}")
            raise HTTPException(
                status_code=429,
                detail="Transcript too large for current LLM tier — wait a moment and try again",
            )
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")
```

- [ ] **Step 3: Add the three new endpoints** (add after the `list_topics_by_call` endpoint)

```python
@router.get("/calls/{call_id}/topics/pending")
async def get_pending(call_id: str):
    """Return validated call topics stored between call_topics and project_matching stages."""
    logger.info(f"📥 [Topics] Pending topics requested: call={call_id}")
    try:
        result = await get_pending_topics(call_id)
        logger.info(f"✅ [Topics] Returned {len(result)} pending topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class MatchGroupPayload(PydanticBaseModel):
    project_topic_id: Optional[str] = None
    call_topic_names: list[str]


@router.post("/calls/{call_id}/topics/save-matches", status_code=200)
async def save_matches(call_id: str, groups: list[MatchGroupPayload]):
    """Save manual match groups and advance to project_updates."""
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save matches failed: {e}")
        raise HTTPException(status_code=500, detail="Save matches failed")


@router.post("/calls/{call_id}/topics/merge-preview")
async def merge_preview(call_id: str):
    """Run parallel LLM merge for all match groups — returns preview, does not save."""
    logger.info(f"📥 [Topics] Merge preview requested: call={call_id}")
    try:
        result = await run_merge_preview(call_id)
        logger.info(f"✅ [Topics] Merge preview: {len(result)} topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Merge preview failed: {e}")
        raise HTTPException(status_code=500, detail="Merge preview failed")


@router.post("/calls/{call_id}/topics/validate-updates")
async def validate_updates(call_id: str, topics: list[dict]):
    """Save reviewed merged topics and advance to artifacts."""
    logger.info(f"📥 [Topics] Validate updates: call={call_id}, count={len(topics)}")
    try:
        result = await validate_project_updates(call_id, topics)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Validate updates failed: {e}")
        raise HTTPException(status_code=500, detail="Validate updates failed")
```

- [ ] **Step 4: Add `Optional` import if not already present**

Check the top of `topics.py` — ensure `from typing import Optional` is present (or that `Optional` is imported from pydantic or typing).

- [ ] **Step 5: Restart backend and smoke-test**

```bash
curl -s http://localhost:8000/api/calls/SOME_CALL_ID/topics/pending
```
Expected: `[]` or a JSON array (not a 500).

---

## Task 4: Frontend — Types and API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

### 4a: Update types

- [ ] **Step 1: Update `KanbanStage` and add `MatchGroup`**

In `frontend/src/types/index.ts`, replace:
```typescript
export type KanbanStage = "transcript" | "call_topics" | "project_topics" | "artifacts" | "done";
```
with:
```typescript
export type KanbanStage = "transcript" | "call_topics" | "project_matching" | "project_updates" | "artifacts" | "done";
```

Add after the `KanbanStage` type:
```typescript
export type MatchGroup = {
  project_topic_id: string | null;   // null = new project topic
  call_topic_names: string[];         // names from pending call topics
};
```

### 4b: Add API methods

- [ ] **Step 2: Add to `topicsAPI` in `frontend/src/api/client.ts`**

Add these methods inside the `topicsAPI` object, after `deleteFromCall`:

```typescript
  getPending: (callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/calls/${callId}/topics/pending`),

  saveMatches: (callId: string, groups: import("@/types").MatchGroup[]) =>
    proxyFetch<{ saved: number }>(`/api/calls/${callId}/topics/save-matches`, {
      method: "POST",
      body: JSON.stringify(groups),
    }),

  mergePreview: (callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/calls/${callId}/topics/merge-preview`, {
      method: "POST",
    }),

  validateUpdates: (callId: string, topics: import("@/types").TopicData[]) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/validate-updates`, {
      method: "POST",
      body: JSON.stringify(topics),
    }),
```

- [ ] **Step 3: TypeScript check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npx tsc --noEmit 2>&1
```
Expected: no errors.

---

## Task 5: Frontend — Update KanbanBoard and Call Page Constants

**Files:**
- Modify: `frontend/src/components/KanbanBoard.tsx`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

### 5a: KanbanBoard

- [ ] **Step 1: Replace STAGES and STAGE_ORDER**

In `KanbanBoard.tsx`, replace:
```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript",     label: "Transcript"     },
  { key: "call_topics",    label: "Call Topics"    },
  { key: "project_topics", label: "Project Topics" },
  { key: "artifacts",      label: "Artifacts"      },
  { key: "done",           label: "Done"           },
];
const STAGE_ORDER: KanbanStage[] = ["transcript", "call_topics", "project_topics", "artifacts", "done"];
```
with:
```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript",      label: "Transcript"       },
  { key: "call_topics",     label: "Call Topics"      },
  { key: "project_matching",label: "Project Matching" },
  { key: "project_updates", label: "Project Updates"  },
  { key: "artifacts",       label: "Artifacts"        },
  { key: "done",            label: "Done"             },
];
const STAGE_ORDER: KanbanStage[] = [
  "transcript", "call_topics", "project_matching", "project_updates", "artifacts", "done"
];
```

- [ ] **Step 2: Update the gate condition** (line that checks `project_topics`)

Find:
```typescript
if ((stageKey === "project_topics" || stageKey === "artifacts" || stageKey === "done") && !prevCallDone) {
```
Replace with:
```typescript
if ((stageKey === "project_matching" || stageKey === "project_updates" || stageKey === "artifacts" || stageKey === "done") && !prevCallDone) {
```

### 5b: Call page

- [ ] **Step 3: Update STAGES and STAGE_LABELS**

In `frontend/app/projects/[id]/calls/[call_id]/page.tsx`, replace:
```typescript
const STAGES = ["transcript", "call_topics", "project_topics", "artifacts", "done"] as const;

const STAGE_LABELS: Record<string, string> = {
  transcript:     "Transcript",
  call_topics:    "Call Topics",
  project_topics: "Project Topics",
  artifacts:      "Artifacts",
  done:           "Done",
};
```
with:
```typescript
const STAGES = ["transcript", "call_topics", "project_matching", "project_updates", "artifacts", "done"] as const;

const STAGE_LABELS: Record<string, string> = {
  transcript:       "Transcript",
  call_topics:      "Call Topics",
  project_matching: "Project Matching",
  project_updates:  "Project Updates",
  artifacts:        "Artifacts",
  done:             "Done",
};
```

- [ ] **Step 4: TypeScript check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npx tsc --noEmit 2>&1
```
Expected: no errors (or only errors about missing stage components — those come in Task 7).

---

## Task 6: Frontend — ProjectMatchingStage Component

**Files:**
- Create: `frontend/src/components/ProjectMatchingStage.tsx`

- [ ] **Step 1: Create the component**

```typescript
"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData, MatchGroup } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  onMatchingComplete: () => void;
};

const PILL: React.CSSProperties = {
  margin: "4px 12px",
  padding: "9px 12px",
  borderRadius: 6,
  border: "1.5px solid #dfe1e6",
  background: "white",
  cursor: "pointer",
  userSelect: "none",
  transition: "border-color .12s, background .12s",
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

export default function ProjectMatchingStage({ callId, projectId, onMatchingComplete }: Props) {
  const [projectTopics, setProjectTopics] = useState<TopicData[]>([]);
  const [callTopics, setCallTopics] = useState<TopicData[]>([]);
  const [selectedLeft, setSelectedLeft] = useState<Set<string>>(new Set()); // topic_id
  const [selectedRight, setSelectedRight] = useState<Set<string>>(new Set()); // name
  const [groups, setGroups] = useState<MatchGroup[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      topicsAPI.listForProject(projectId),
      topicsAPI.getPending(callId),
    ]).then(([proj, pending]) => {
      setProjectTopics(proj);
      setCallTopics(pending);
    }).catch(() => setError("Failed to load topics"));
  }, [callId, projectId]);

  // Which project topic IDs have been matched
  const matchedProjectIds = new Set(groups.map((g) => g.project_topic_id).filter(Boolean) as string[]);
  // Which call topic names have been matched or marked new
  const accountedCallNames = new Set(groups.flatMap((g) => g.call_topic_names));

  function toggleLeft(id: string) {
    if (matchedProjectIds.has(id)) return;
    setSelectedLeft((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleRight(name: string) {
    if (accountedCallNames.has(name)) return;
    setSelectedRight((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function handleLink() {
    if (selectedRight.size === 0 || selectedLeft.size === 0) return;
    const projectTopicId = [...selectedLeft][0]; // 1:N — one project topic
    setGroups((prev) => [
      ...prev,
      { project_topic_id: projectTopicId, call_topic_names: [...selectedRight] },
    ]);
    setSelectedLeft(new Set());
    setSelectedRight(new Set());
  }

  function handleMarkNew() {
    if (selectedRight.size === 0) return;
    setGroups((prev) => [
      ...prev,
      { project_topic_id: null, call_topic_names: [...selectedRight] },
    ]);
    setSelectedRight(new Set());
  }

  function removeGroup(idx: number) {
    setGroups((prev) => prev.filter((_, i) => i !== idx));
  }

  const allCallTopicsAccounted = callTopics.length > 0 &&
    callTopics.every((t) => accountedCallNames.has(t.name));

  const pendingCount = callTopics.filter((t) => !accountedCallNames.has(t.name)).length;

  async function handleDone() {
    setSaving(true);
    setError(null);
    try {
      await topicsAPI.saveMatches(callId, groups);
      logger.info(`✅ [ProjectMatching] Saved ${groups.length} groups`, { component: "ProjectMatchingStage" });
      onMatchingComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save matches");
    } finally {
      setSaving(false);
    }
  }

  // Find which group a project topic is matched to
  function getProjectTopicGroup(id: string): MatchGroup | undefined {
    return groups.find((g) => g.project_topic_id === id);
  }

  // Find which group a call topic is in
  function getCallTopicGroup(name: string): MatchGroup | undefined {
    return groups.find((g) => g.call_topic_names.includes(name));
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Matching
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84" }}>
          Step 1 of 2 — Match this call's topics to existing project topics, or mark as new.
        </div>
      </div>

      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      {/* Two-column body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT — existing project topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", borderRight: "1px solid #dfe1e6" }}>
          <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              Existing Project Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>{projectTopics.length} topics</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {projectTopics.map((t) => {
              const group = getProjectTopicGroup(t.topic_id ?? "");
              const isSelected = selectedLeft.has(t.topic_id ?? "");
              const isMatched = !!group;
              return (
                <div
                  key={t.topic_id}
                  onClick={() => toggleLeft(t.topic_id ?? "")}
                  style={{
                    ...PILL,
                    borderColor: isMatched ? "#36b37e" : isSelected ? "#0052cc" : "#dfe1e6",
                    background: isMatched ? "#e3fcef" : isSelected ? "#e9f0ff" : "white",
                    cursor: isMatched ? "default" : "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {t.status && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3, ...(STATUS_BADGE[t.status] ?? STATUS_BADGE.open) }}>
                        {t.status.replace("_", " ")}
                      </span>
                    )}
                    {isMatched && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3, background: "#e3fcef", color: "#006644" }}>
                        Matched
                      </span>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {isMatched && (
                    <div style={{ fontSize: 10, color: "#36b37e", fontWeight: 600, marginTop: 4 }}>
                      ↔ {group.call_topic_names.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* CENTER — action buttons */}
        <div style={{ width: 72, flexShrink: 0, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", background: "#fafbfc",
          borderRight: "1px solid #dfe1e6", gap: 8, padding: "12px 0" }}>
          <button
            onClick={handleLink}
            disabled={selectedLeft.size === 0 || selectedRight.size === 0}
            title="Link selected topics"
            style={{
              writingMode: "vertical-rl", textOrientation: "mixed",
              fontSize: 11, fontWeight: 700,
              background: (selectedLeft.size > 0 && selectedRight.size > 0) ? "#0052cc" : "#f4f5f7",
              color: (selectedLeft.size > 0 && selectedRight.size > 0) ? "white" : "#97a0af",
              border: "none", padding: "12px 8px", borderRadius: 6,
              cursor: (selectedLeft.size > 0 && selectedRight.size > 0) ? "pointer" : "default",
              letterSpacing: ".04em", fontFamily: "inherit",
            }}
          >
            Link ↔
          </button>
          <button
            onClick={handleMarkNew}
            disabled={selectedRight.size === 0}
            title="Mark as new project topic"
            style={{
              writingMode: "vertical-rl", textOrientation: "mixed",
              fontSize: 11, fontWeight: 600,
              background: "white",
              color: selectedRight.size > 0 ? "#172b4d" : "#97a0af",
              border: `1px solid ${selectedRight.size > 0 ? "#97a0af" : "#dfe1e6"}`,
              padding: "12px 8px", borderRadius: 6,
              cursor: selectedRight.size > 0 ? "pointer" : "default",
              fontFamily: "inherit",
            }}
          >
            New →
          </button>
        </div>

        {/* RIGHT — this call's topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              This Call's Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>
              {callTopics.length - pendingCount} matched · {pendingCount} pending
            </span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {callTopics.map((t) => {
              const group = getCallTopicGroup(t.name);
              const isSelected = selectedRight.has(t.name);
              const isAccounted = accountedCallNames.has(t.name);
              return (
                <div
                  key={t.name}
                  onClick={() => toggleRight(t.name)}
                  style={{
                    ...PILL,
                    borderColor: isAccounted ? "#79dbb2" : isSelected ? "#0052cc" : "#dfe1e6",
                    background: isAccounted ? "#f0fdf7" : isSelected ? "#e9f0ff" : "white",
                    cursor: isAccounted ? "default" : "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {isAccounted && group && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        background: group.project_topic_id ? "#e3fcef" : "#f0f0f0",
                        color: group.project_topic_id ? "#006644" : "#5e6c84" }}>
                        {group.project_topic_id ? "Matched" : "New Topic"}
                      </span>
                    )}
                    {isAccounted && (
                      <button
                        onClick={(e) => { e.stopPropagation(); removeGroup(groups.indexOf(group!)); }}
                        title="Remove match"
                        style={{ marginLeft: "auto", fontSize: 10, color: "#bfc5ce",
                          background: "none", border: "none", cursor: "pointer" }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {isAccounted && group?.project_topic_id && (
                    <div style={{ fontSize: 10, color: "#36b37e", fontWeight: 600, marginTop: 4 }}>
                      ↔ {projectTopics.find((p) => p.topic_id === group.project_topic_id)?.name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* Action bar */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <span style={{ fontSize: 12, color: "#5e6c84" }}>
          {allCallTopicsAccounted ? (
            <span style={{ color: "#36b37e", fontWeight: 600 }}>✓ All call topics accounted for</span>
          ) : (
            <><strong style={{ color: "#172b4d" }}>{pendingCount}</strong> call topic{pendingCount !== 1 ? "s" : ""} still need matching</>
          )}
        </span>
        <button
          onClick={handleDone}
          disabled={!allCallTopicsAccounted || saving}
          style={{
            padding: "8px 22px", borderRadius: 6, border: "none",
            background: allCallTopicsAccounted && !saving ? "#0052cc" : "#f4f5f7",
            color: allCallTopicsAccounted && !saving ? "white" : "#97a0af",
            fontSize: 13, fontWeight: 600,
            cursor: allCallTopicsAccounted && !saving ? "pointer" : "default",
            fontFamily: "inherit",
          }}
        >
          {saving ? "Saving…" : "Done Matching →"}
        </button>
      </div>

    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npx tsc --noEmit 2>&1
```
Expected: no errors.

---

## Task 7: Frontend — ProjectUpdatesStage Component

**Files:**
- Create: `frontend/src/components/ProjectUpdatesStage.tsx`

- [ ] **Step 1: Create the component**

```typescript
"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData } from "@/types";

type Props = {
  callId: string;
  onValidated: () => void;
};

const SEL: React.CSSProperties = {
  fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4,
  padding: "3px 7px", background: "white", color: "#172b4d",
  fontFamily: "inherit", cursor: "pointer",
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#216e4e", neutral: "#5e6c84", concern: "#ae2a19",
};

type TopicRowProps = {
  topic: TopicData;
  onChange: (t: TopicData) => void;
};

function TopicRow({ topic, onChange }: TopicRowProps) {
  const [expanded, setExpanded] = useState(false);
  const isNew = !topic.topic_id;

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      paddingLeft: expanded ? 17 : 20,
      paddingRight: 20,
      paddingTop: 10,
      paddingBottom: 10,
      borderLeft: expanded ? "3px solid #0052cc" : `3px solid ${isNew ? "#79dbb2" : "transparent"}`,
      background: expanded ? "#fafbfc" : "white",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flex: 1, minWidth: 0 }}>
          {expanded ? (
            <input
              value={topic.name}
              onChange={(e) => onChange({ ...topic, name: e.target.value })}
              style={{ fontSize: 13, fontWeight: 600, color: "#172b4d",
                border: "none", borderBottom: "2px solid #0052cc", outline: "none",
                background: "transparent", flex: 1, minWidth: 0, fontFamily: "inherit" }}
            />
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{topic.name}</span>
          )}
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
            ...(STATUS_BADGE[topic.status ?? "open"] ?? STATUS_BADGE.open) }}>
            {(topic.status ?? "open").replace("_", " ")}
          </span>
          {isNew && (
            <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
              padding: "2px 6px", borderRadius: 3, background: "#f0fdf7", color: "#36b37e", flexShrink: 0 }}>
              New
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
            color: SENTIMENT_COLOR[topic.sentiment ?? "neutral"] ?? "#5e6c84" }}>
            {topic.sentiment}
          </span>
          <button onClick={() => setExpanded((v) => !v)}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13,
              padding: "0 2px", color: expanded ? "#0052cc" : "#97a0af", lineHeight: 1 }}>
            ✎
          </button>
        </div>
      </div>

      {!expanded && topic.summary && (
        <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>
          {topic.summary}
        </p>
      )}
      {!expanded && (topic.follow_up_items ?? []).map((item, i) => (
        <div key={i} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
      ))}

      {expanded && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={topic.status ?? "open"} onChange={(e) => onChange({ ...topic, status: e.target.value as TopicData["status"] })} style={SEL}>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
            <select value={topic.owner ?? "Us"} onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicData["owner"] })} style={SEL}>
              <option value="Us">Us</option>
              <option value="Client">Client</option>
              <option value="Both">Both</option>
            </select>
            <select value={topic.sentiment ?? "neutral"} onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicData["sentiment"] })} style={SEL}>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="concern">Concern</option>
            </select>
          </div>
          <textarea
            value={topic.summary ?? ""}
            onChange={(e) => onChange({ ...topic, summary: e.target.value })}
            placeholder="Summary…"
            rows={3}
            style={{ fontSize: 12, color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
              padding: "6px 8px", resize: "vertical", fontFamily: "inherit",
              width: "100%", boxSizing: "border-box" }}
          />
          <div>
            {(topic.follow_up_items ?? []).map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ color: "#97a0af", fontSize: 11 }}>→</span>
                <input value={item}
                  onChange={(e) => {
                    const items = [...(topic.follow_up_items ?? [])];
                    items[i] = e.target.value;
                    onChange({ ...topic, follow_up_items: items });
                  }}
                  style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
                />
                <button onClick={() => onChange({ ...topic, follow_up_items: (topic.follow_up_items ?? []).filter((_, idx) => idx !== i) })}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#bfc5ce", fontSize: 11 }}>✕</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProjectUpdatesStage({ callId, onValidated }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  async function handleRunMerge() {
    setLoading(true);
    setError(null);
    try {
      logger.info("Running merge preview", { component: "ProjectUpdatesStage" });
      const result = await topicsAPI.mergePreview(callId);
      setTopics(result);
      setRan(true);
      logger.info(`Merge preview: ${result.length} topics`, { component: "ProjectUpdatesStage" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleValidate() {
    setValidating(true);
    setError(null);
    try {
      await topicsAPI.validateUpdates(callId, topics);
      onValidated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Updates
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84" }}>
          Step 2 of 2 — Review LLM-merged topic updates before saving to the project.
        </div>
      </div>

      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      {!ran ? (
        <div style={{ padding: 20, flexShrink: 0 }}>
          <p style={{ fontSize: 13, color: "#5e6c84", marginBottom: 16, marginTop: 0 }}>
            Run the merge to generate updated topic content based on your matching decisions.
            New topics will be created directly; matched topics will be merged with their existing summaries.
          </p>
          <button
            onClick={handleRunMerge}
            disabled={loading}
            style={{ padding: "10px 22px", borderRadius: 6, border: "none",
              background: loading ? "#f4f5f7" : "#0052cc",
              color: loading ? "#97a0af" : "white",
              cursor: loading ? "default" : "pointer",
              fontSize: 13, fontWeight: 600, fontFamily: "inherit" }}
          >
            {loading ? "Merging…" : "Run Merge"}
          </button>
        </div>
      ) : (
        <>
          <div style={{ padding: "10px 20px 6px", fontSize: 11, fontWeight: 700, color: "#5e6c84",
            textTransform: "uppercase", letterSpacing: ".05em", borderBottom: "1px solid #f4f5f7", flexShrink: 0 }}>
            Topics ({topics.length})
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {topics.map((t, i) => (
              <TopicRow
                key={t.topic_id ?? t.name ?? i}
                topic={t}
                onChange={(updated) => {
                  const next = [...topics];
                  next[i] = updated;
                  setTopics(next);
                }}
              />
            ))}
          </div>
          <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
            display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
            <button
              onClick={handleRunMerge}
              disabled={loading}
              style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                background: "white", color: "#5e6c84", fontSize: 12, cursor: loading ? "default" : "pointer",
                fontFamily: "inherit" }}
            >
              {loading ? "Re-running…" : "Re-run Merge"}
            </button>
            <button
              onClick={handleValidate}
              disabled={validating || topics.length === 0}
              style={{ padding: "8px 22px", borderRadius: 6, border: "none",
                background: validating || topics.length === 0 ? "#f4f5f7" : "#0052cc",
                color: validating || topics.length === 0 ? "#97a0af" : "white",
                fontSize: 13, fontWeight: 600,
                cursor: validating || topics.length === 0 ? "default" : "pointer",
                fontFamily: "inherit" }}
            >
              {validating ? "Saving…" : "Validate →"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npx tsc --noEmit 2>&1
```
Expected: no errors.

---

## Task 8: Frontend — Wire New Stages into Call Page

**Files:**
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

- [ ] **Step 1: Add imports**

Add at the top of the file alongside existing stage imports:
```typescript
import ProjectMatchingStage from "@/components/ProjectMatchingStage";
import ProjectUpdatesStage from "@/components/ProjectUpdatesStage";
```

- [ ] **Step 2: Update the `onAggregateComplete` handler in CallTopicsStage**

Currently `CallTopicsStage` calls `onAggregateComplete(result)` which expects the old 3-bucket result. The aggregate endpoint now returns `{advanced_to: "project_matching"}` for Call 2+. Update the handler:

Find:
```typescript
{call.kanban_stage === "call_topics" && (
  <CallTopicsStage
    call={call}
    onAggregateComplete={(result) => {
      ...
    }}
    onAutoAdvanced={() => {
      loadCall();
    }}
  />
)}
```

Replace the entire `onAggregateComplete` handler to just reload the call (since aggregate now advances the stage itself):
```typescript
{call.kanban_stage === "call_topics" && (
  <CallTopicsStage
    call={call}
    onAggregateComplete={() => loadCall()}
    onAutoAdvanced={() => loadCall()}
  />
)}
```

- [ ] **Step 3: Update `CallTopicsStage` Props type**

In `frontend/src/components/CallTopicsStage.tsx`, update the Props type:
```typescript
type Props = {
  call: Call;
  onAggregateComplete: () => void;   // was: (result: AggregateResult) => void
  onAutoAdvanced: () => void;
};
```

And in `handleContinue`, replace:
```typescript
      if (result.auto_advanced) {
        ...
        onAutoAdvanced();
      } else {
        onAggregateComplete(result);
      }
```
with:
```typescript
      if (result.auto_advanced) {
        logger.info("Call 1 auto-advanced to artifacts", { component: "CallTopicsStage" });
        onAutoAdvanced();
      } else {
        // Call 2+ advanced to project_matching
        onAggregateComplete();
      }
```

- [ ] **Step 4: Add the two new stage blocks**

In the call page JSX, after the `call_topics` block and before the `artifacts` block, add:

```typescript
        {call.kanban_stage === "project_matching" && (
          <ProjectMatchingStage
            callId={call.id}
            projectId={call.project_id}
            onMatchingComplete={() => loadCall()}
          />
        )}

        {call.kanban_stage === "project_updates" && (
          <ProjectUpdatesStage
            callId={call.id}
            onValidated={() => loadCall()}
          />
        )}
```

- [ ] **Step 5: Update historical view logic**

Find the `viewStage === "project_topics"` block (around line 205) and update it to handle both new stages. Replace:

```typescript
  // Project Topics-only mode: navigated from a historical project_topics card
  if (viewStage === "project_topics") {
```
with:
```typescript
  // Project updates history view (project_matching or project_updates stages)
  if (viewStage === "project_matching" || viewStage === "project_updates") {
```

And update the content it renders to use `TopicsPanel` with `callScoped`:
```typescript
  if (viewStage === "project_matching" || viewStage === "project_updates") {
    return (
      <div style={{ flex: 1, overflow: "auto", padding: 20 }}>
        <TopicsPanel callId={call.id} projectId={call.project_id} defaultOpen callScoped
          call={call} />
      </div>
    );
  }
```

- [ ] **Step 6: Remove `AggregateResult` import if it's now unused**

Check if `AggregateResult` is still imported in `CallTopicsStage.tsx` and the call page — remove if unused.

- [ ] **Step 7: TypeScript check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend" && npx tsc --noEmit 2>&1
```
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: add project_matching and project_updates stages with manual topic linking"
```

---

## Task 9: End-to-End Smoke Test

- [ ] **Step 1: Start backend and frontend**

```bash
# Terminal 1
cd "/Users/louisgarnier/Claude/Project management" && python3 -m backend.main

# Terminal 2
cd "/Users/louisgarnier/Claude/Project management/frontend" && npm run dev
```

- [ ] **Step 2: Test Call 1 flow (unchanged)**
  1. Create a new project → create Call 1 → add transcript
  2. Go through `call_topics` → Extract → Continue →
  3. Verify it auto-advances directly to `artifacts` (skips both new stages)
  4. Complete artifacts → verify call reaches `done`

- [ ] **Step 3: Test Call 2 flow (new stages)**
  1. Create Call 2 → add transcript
  2. Go through `call_topics` → Extract → Continue →
  3. Verify call advances to `project_matching` stage
  4. In project_matching: click a right topic, click a left topic → Link button activates → click Link → verify they show as matched
  5. Click a right topic with no match → click "New →" → verify it shows as "New Topic"
  6. Once all right topics are accounted for → "Done Matching →" becomes active → click it
  7. Verify call advances to `project_updates` stage
  8. Click "Run Merge" → verify topics appear with merged content
  9. Edit a topic summary → click "Validate →"
  10. Verify call advances to `artifacts`

- [ ] **Step 4: Test refresh persistence in project_matching**
  1. Start matching on Call 2 → link 1-2 topics → refresh page
  2. Verify previously linked topics are still shown as matched (loaded from `topic_match_groups` DB)

  > Note: the current `ProjectMatchingStage` loads `topic_match_groups` from `getPending` but does NOT reload saved match groups on mount. If refresh persistence is required, add a `GET /calls/{call_id}/topics/match-groups` endpoint and load it on mount.

- [ ] **Step 5: Verify KanbanBoard shows 6 columns**

  Open the board view — confirm 6 columns: Transcript, Call Topics, Project Matching, Project Updates, Artifacts, Done.
