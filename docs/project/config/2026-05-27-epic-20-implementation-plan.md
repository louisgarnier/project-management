# EPIC-20 Implementation Plan — Three-Stage Call Processing

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace EPIC-19's single mashed-up matching screen with three sequenced stages: Topic Confirmation → Task Grouping → Project Updates.

**Architecture:** Stage 1 produces a finalized topic list (user decides which topics are alive). Stage 2 takes that list + all tasks (old + new) and runs an LLM auto-cluster pass to build small task groups, each scoped to one topic; user drags to override. Stage 3 routes the 3 existing passes (1, 2, 3) by group composition (new-only / old-only / mixed).

**Tech Stack:** Next.js 15 + React 19, Python 3.11 + FastAPI + Supabase Postgres, OpenRouter LLM (Sonnet 4.6 default). All existing patterns preserved (v5 atomic-task pipeline, line-number citations, color-coded groups).

**Predecessor:** EPIC-19 — drag-to-section plumbing and multi-topic primary-target logic get deleted.

---

## Pre-flight: locked decisions

1. **Old-only groups:** one bag per topic (no sub-clustering of previous-call tasks)
2. **Stage 2 LLM scope:** one global call per call-id; finalized topic list passed as a fixed enum
3. **Stage 1 rename propagation:** immediate write to `topic_registry.name` (not a per-call alias)
4. **Stage 2 re-run policy:** preserve groups when topics change; only re-cluster on explicit user click
5. **LLM proposals persistence:** immediate draft save (same pattern as current task matching)
6. **Stage 1 UI:** two columns (existing | new candidates) with keep/rename/merge/drop actions

---

## Phase 1 — Data model & migrations

### Task 1: Migration 037 — `call_finalized_topics` table

**Files:**
- Create: `backend/database/migrations/037_call_finalized_topics.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 037 — EPIC-20 Stage 1: per-call finalized topic list
-- Holds the user's topic-lifecycle decisions for each call.

create table if not exists call_finalized_topics (
    id           uuid primary key default gen_random_uuid(),
    call_id      uuid not null references calls(id) on delete cascade,
    -- For "keep existing" entries: topic_id points at the project topic.
    -- For "introduce new" entries: topic_id is null until the topic is materialized in topic_registry.
    topic_id     uuid references topic_registry(id) on delete set null,
    name         text not null,
    -- 'existing' = a project topic carried forward (possibly renamed)
    -- 'new'      = a new topic introduced this call
    source       text not null check (source in ('existing','new')),
    -- Optional pointer to the v5 cluster that proposed this topic (audit only)
    v5_cluster_id text,
    position     int not null default 0,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index if not exists idx_cft_call_id on call_finalized_topics(call_id);
create unique index if not exists uniq_cft_call_name on call_finalized_topics(call_id, name);

-- PostgREST schema reload — required for column visibility
notify pgrst, 'reload schema';
```

- [ ] **Step 2: Commit the migration file**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: migration 037 — call_finalized_topics table"
```

- [ ] **Step 3: Surface manual run to user**

Output a note in the task summary: "Run migration 037 in Supabase Dashboard before testing Stage 1."

---

### Task 2: Migration 038 — simplify `topic_match_groups`

**Files:**
- Create: `backend/database/migrations/038_topic_match_groups_simplify.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 038 — EPIC-20 Stage 2: one topic per group; explicit kind enum
-- Replaces EPIC-19's multi-topic primary-target hack.

-- Add new columns (nullable for backfill).
alter table topic_match_groups
    add column if not exists finalized_topic_id uuid references call_finalized_topics(id) on delete cascade,
    add column if not exists group_kind text check (group_kind in ('new_only','old_only','mixed'));

create index if not exists idx_tmg_finalized_topic on topic_match_groups(finalized_topic_id);

-- Backfill script will populate finalized_topic_id + group_kind for existing rows.
-- After backfill, deprecate (but don't drop) the multi-topic columns to keep rollback safe:
--   project_topic_ids, target_topic_name, project_task_refs (multi-topic semantics)
-- These columns remain on the table but new code paths ignore them.

notify pgrst, 'reload schema';
```

- [ ] **Step 2: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: migration 038 — topic_match_groups simplification (finalized_topic_id + kind)"
```

---

### Task 3: TypedDict + service for `call_finalized_topics`

**Files:**
- Create: `backend/services/finalized_topics_service.py`
- Test: `backend/tests/test_finalized_topics_service.py`

- [ ] **Step 1: Write the failing test first**

```python
# backend/tests/test_finalized_topics_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.finalized_topics_service import (
    FinalizedTopic,
    save_finalized_topics,
    load_finalized_topics,
)


@pytest.mark.asyncio
async def test_save_replaces_existing_set():
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
    mock_supabase.table.return_value.insert.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
    topics: list[FinalizedTopic] = [
        {"name": "ARM", "source": "existing", "topic_id": "uuid-1"},
        {"name": "Stress Testing", "source": "new", "topic_id": None},
    ]
    await save_finalized_topics(mock_supabase, "call-uuid", topics)
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.assert_awaited_once()
    mock_supabase.table.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_load_returns_ordered_list():
    mock_supabase = MagicMock()
    mock_resp = MagicMock(data=[
        {"id": "a", "name": "ARM", "source": "existing", "topic_id": "uuid-1", "position": 0},
        {"id": "b", "name": "New Topic", "source": "new", "topic_id": None, "position": 1},
    ])
    mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute = AsyncMock(return_value=mock_resp)
    out = await load_finalized_topics(mock_supabase, "call-uuid")
    assert len(out) == 2
    assert out[0]["name"] == "ARM"
    assert out[1]["source"] == "new"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_finalized_topics_service.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Implement the service**

```python
# backend/services/finalized_topics_service.py
"""EPIC-20 Stage 1: per-call finalized topic list — CRUD."""
from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger("calltracker.finalized_topics")


class FinalizedTopic(TypedDict, total=False):
    id: str           # uuid, server-generated on insert
    name: str
    source: str       # 'existing' | 'new'
    topic_id: str | None
    v5_cluster_id: str | None
    position: int


async def load_finalized_topics(supabase, call_id: str) -> list[FinalizedTopic]:
    """Load the finalized topic list for a call, ordered by position."""
    resp = await (
        supabase.table("call_finalized_topics")
        .select("id, name, source, topic_id, v5_cluster_id, position")
        .eq("call_id", call_id)
        .order("position")
        .execute()
    )
    return list(resp.data or [])


async def save_finalized_topics(
    supabase, call_id: str, topics: list[FinalizedTopic]
) -> None:
    """Replace the full finalized topic list for a call.

    Delete-then-insert (transactional via PostgREST single request would be
    ideal, but Supabase Python lib doesn't expose transactions — accept the
    risk of a partial state on failure; the UI re-loads after save so any
    inconsistency is visible).
    """
    logger.info("🗄️  save_finalized_topics: %d topics for call %s", len(topics), call_id)
    await (
        supabase.table("call_finalized_topics")
        .delete()
        .eq("call_id", call_id)
        .execute()
    )
    if not topics:
        return
    rows = []
    for i, t in enumerate(topics):
        rows.append({
            "call_id": call_id,
            "name": t["name"],
            "source": t.get("source", "existing"),
            "topic_id": t.get("topic_id"),
            "v5_cluster_id": t.get("v5_cluster_id"),
            "position": i,
        })
    await supabase.table("call_finalized_topics").insert(rows).execute()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest backend/tests/test_finalized_topics_service.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: finalized_topics_service — load/save per-call topic list"
```

---

### Task 4: Extend `task_match_persistence.py` for new schema

**Files:**
- Modify: `backend/services/task_match_persistence.py`
- Test: `backend/tests/test_task_match_persistence_v2.py`

- [ ] **Step 1: Write failing test for new shape**

```python
# backend/tests/test_task_match_persistence_v2.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.task_match_persistence import (
    save_task_match_groups,
    TaskMatchGroup,
)


@pytest.mark.asyncio
async def test_save_uses_finalized_topic_id_and_group_kind():
    """EPIC-20: each group has exactly one finalized_topic_id + a group_kind."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
    mock_supabase.table.return_value.insert.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
    groups: list[TaskMatchGroup] = [
        {
            "id": "g1",
            "finalized_topic_id": "ft1",
            "group_kind": "new_only",
            "call_task_refs": [{"task_id": "t1"}],
            "project_task_refs": [],
        },
        {
            "id": "g2",
            "finalized_topic_id": "ft2",
            "group_kind": "mixed",
            "call_task_refs": [{"task_id": "t2"}],
            "project_task_refs": [{"project_topic_id": "p1", "task_id": "pt1"}],
        },
    ]
    await save_task_match_groups(mock_supabase, "call-uuid", groups, draft=True)
    insert_call = mock_supabase.table.return_value.insert.call_args
    rows = insert_call.args[0]
    assert rows[0]["finalized_topic_id"] == "ft1"
    assert rows[0]["group_kind"] == "new_only"
    assert rows[1]["group_kind"] == "mixed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest backend/tests/test_task_match_persistence_v2.py -v`
Expected: FAIL — `finalized_topic_id` not in the persisted row.

- [ ] **Step 3: Extend the TypedDict + save function**

Edit `backend/services/task_match_persistence.py`:

```python
# Add to TaskMatchGroup TypedDict:
class TaskMatchGroup(TypedDict, total=False):
    id: str
    finalized_topic_id: str            # EPIC-20: exactly one target topic
    group_kind: str                    # 'new_only' | 'old_only' | 'mixed'
    call_task_refs: list[dict]
    project_task_refs: list[dict]
    # EPIC-19 fields kept temporarily for rollback safety (ignored by new code):
    project_topic_ids: list[str]
    target_topic_name: str | None
    kind: str
```

In `save_task_match_groups`, when building the row dict:

```python
row = {
    "call_id": call_id,
    "id": g.get("id"),
    "finalized_topic_id": g.get("finalized_topic_id"),
    "group_kind": g.get("group_kind") or _infer_kind(g),
    "call_task_refs": g.get("call_task_refs", []),
    "project_task_refs": g.get("project_task_refs", []),
    "draft": draft,
}
```

Add helper:

```python
def _infer_kind(g: TaskMatchGroup) -> str:
    has_call = bool(g.get("call_task_refs"))
    has_proj = bool(g.get("project_task_refs"))
    if has_call and has_proj:
        return "mixed"
    if has_call:
        return "new_only"
    if has_proj:
        return "old_only"
    return "new_only"  # empty group → treat as placeholder for new
```

- [ ] **Step 4: Run test, verify PASS**

Run: `pytest backend/tests/test_task_match_persistence_v2.py -v`

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: task_match_persistence — finalized_topic_id + group_kind"
```

---

### Task 5: Backfill script for existing calls

**Files:**
- Create: `backend/scripts/backfill_finalized_topics.py`

- [ ] **Step 1: Write the backfill script**

```python
# backend/scripts/backfill_finalized_topics.py
"""EPIC-20 backfill — populate call_finalized_topics + finalized_topic_id for
all calls that have existing topic_match_groups under EPIC-19 schema.

For each call:
  1. Collect distinct target topics from existing match groups
     (use project_topic_ids[0] + target_topic_name as canonical name)
  2. INSERT one row into call_finalized_topics per topic
  3. UPDATE each topic_match_group with the corresponding finalized_topic_id
  4. Compute group_kind from call_task_refs + project_task_refs shape
"""
from __future__ import annotations

import asyncio
import logging
import sys

from backend.database.supabase_client import get_supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")


async def backfill_call(supabase, call_id: str) -> None:
    groups_resp = await (
        supabase.table("topic_match_groups")
        .select("id, call_task_refs, project_task_refs, project_topic_ids, target_topic_name")
        .eq("call_id", call_id)
        .execute()
    )
    groups = groups_resp.data or []
    if not groups:
        logger.info("call %s: no groups, skip", call_id)
        return

    # 1. Collect topics (name keyed; first wins)
    topics_by_name: dict[str, dict] = {}
    for g in groups:
        name = (g.get("target_topic_name") or "").strip()
        topic_id = (g.get("project_topic_ids") or [None])[0]
        if not name and topic_id:
            t = await supabase.table("topic_registry").select("name").eq("id", topic_id).single().execute()
            name = (t.data or {}).get("name", "")
        if not name:
            name = "(unnamed)"
        if name not in topics_by_name:
            topics_by_name[name] = {
                "name": name,
                "source": "existing" if topic_id else "new",
                "topic_id": topic_id,
            }

    # 2. Insert finalized topics
    rows = [
        {"call_id": call_id, "name": t["name"], "source": t["source"],
         "topic_id": t["topic_id"], "position": i}
        for i, t in enumerate(topics_by_name.values())
    ]
    if rows:
        inserted = await supabase.table("call_finalized_topics").upsert(rows).execute()
        ft_by_name = {r["name"]: r["id"] for r in (inserted.data or [])}
    else:
        ft_by_name = {}

    # 3+4. Update each group
    for g in groups:
        name = (g.get("target_topic_name") or "").strip()
        if not name:
            topic_id = (g.get("project_topic_ids") or [None])[0]
            if topic_id:
                t = await supabase.table("topic_registry").select("name").eq("id", topic_id).single().execute()
                name = (t.data or {}).get("name", "(unnamed)")
            else:
                name = "(unnamed)"
        ftid = ft_by_name.get(name)
        has_call = bool(g.get("call_task_refs"))
        has_proj = bool(g.get("project_task_refs"))
        kind = "mixed" if (has_call and has_proj) else ("new_only" if has_call else "old_only")
        await supabase.table("topic_match_groups").update({
            "finalized_topic_id": ftid,
            "group_kind": kind,
        }).eq("id", g["id"]).execute()

    logger.info("✅ call %s: backfilled %d topics, %d groups", call_id, len(rows), len(groups))


async def main():
    supabase = get_supabase()
    calls_resp = await supabase.table("calls").select("id").execute()
    for c in (calls_resp.data or []):
        try:
            await backfill_call(supabase, c["id"])
        except Exception as e:
            logger.error("❌ call %s: %s", c["id"], e)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit (do not run yet — user runs manually after migrations 037+038)**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: backfill_finalized_topics — populate EPIC-20 columns from EPIC-19 data"
```

---

## Phase 2 — Stage 1 (Topic confirmation) backend + UI

### Task 6: Add `topic_confirmation` kanban stage to enum

**Files:**
- Modify: `backend/services/kanban_stages.py` (or wherever stages enum lives)
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Locate the stages enum in backend**

```bash
grep -rn "kanban_stage" backend/ | grep -i "enum\|literal" | head -5
```

- [ ] **Step 2: Insert `topic_confirmation` between `call_topics` and `project_matching`**

Backend (typical shape):

```python
KANBAN_STAGES = [
    "extract",
    "call_topics",
    "topic_confirmation",   # NEW — EPIC-20 Stage 1
    "project_matching",     # will be renamed task_grouping in Task 14
    "project_updates",
    "artifacts",
]
```

Frontend `types/index.ts`:

```typescript
export type KanbanStage =
  | "extract"
  | "call_topics"
  | "topic_confirmation"      // EPIC-20 Stage 1
  | "project_matching"
  | "project_updates"
  | "artifacts";
```

- [ ] **Step 3: Run type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: add topic_confirmation kanban stage"
```

---

### Task 7: Endpoint `GET /calls/{id}/topic-confirmation`

**Files:**
- Modify: `backend/routers/topics.py` (or appropriate router)
- Test: `backend/tests/test_topic_confirmation_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_topic_confirmation_endpoint.py
import pytest
from httpx import AsyncClient
from backend.main import app


@pytest.mark.asyncio
async def test_get_topic_confirmation_returns_two_buckets(monkeypatch):
    """Endpoint returns existing project topics + v5 new-topic candidates."""
    async def fake_load(supabase, call_id):
        return {
            "existing": [{"topic_id": "t1", "name": "ARM", "tasks_count": 3}],
            "new_candidates": [{"name": "Stress Testing", "v5_cluster_id": "c1"}],
            "finalized": [],  # empty on first load
        }
    monkeypatch.setattr(
        "backend.routers.topics.get_topic_confirmation_payload",
        fake_load,
    )
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/calls/call-uuid/topic-confirmation")
    assert resp.status_code == 200
    body = resp.json()
    assert "existing" in body
    assert "new_candidates" in body
    assert "finalized" in body
```

- [ ] **Step 2: Run test (expect FAIL — endpoint doesn't exist)**

- [ ] **Step 3: Implement the endpoint + payload builder**

In `backend/routers/topics.py`:

```python
@router.get("/api/calls/{call_id}/topic-confirmation")
async def get_topic_confirmation(call_id: str, supabase = Depends(get_supabase)):
    return await get_topic_confirmation_payload(supabase, call_id)


async def get_topic_confirmation_payload(supabase, call_id: str) -> dict:
    """Build the Stage 1 payload: existing project topics + v5 new candidates + saved finalized."""
    # 1. existing project topics (from project_topic_state view)
    call = await supabase.table("calls").select("project_id").eq("id", call_id).single().execute()
    project_id = call.data["project_id"]
    existing_resp = await (
        supabase.table("project_topic_state")
        .select("topic_id, name, tasks")
        .eq("project_id", project_id)
        .execute()
    )
    existing = [
        {"topic_id": t["topic_id"], "name": t["name"], "tasks_count": len(t.get("tasks", []))}
        for t in (existing_resp.data or [])
    ]
    # 2. v5 new-topic candidates (from call_topics v5 Stage 5 output stored on calls)
    ct_resp = await (
        supabase.table("calls")
        .select("call_topics_v5")
        .eq("id", call_id)
        .single()
        .execute()
    )
    v5 = (ct_resp.data or {}).get("call_topics_v5") or {}
    new_candidates = [
        {"name": c["topic_name"], "v5_cluster_id": c.get("cluster_id"), "task_count": len(c.get("unit_ids", []))}
        for c in v5.get("clusters", [])
        if c.get("new_topic")
    ]
    # 3. Already-saved finalized list (if user is returning to Stage 1)
    finalized = await load_finalized_topics(supabase, call_id)
    return {"existing": existing, "new_candidates": new_candidates, "finalized": finalized}
```

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: GET /calls/{id}/topic-confirmation endpoint"
```

---

### Task 8: Endpoint `POST /calls/{id}/topic-confirmation/save`

**Files:**
- Modify: `backend/routers/topics.py`
- Test: extend `backend/tests/test_topic_confirmation_endpoint.py`

- [ ] **Step 1: Add the failing test case**

```python
@pytest.mark.asyncio
async def test_save_finalized_topics_and_propagates_renames(monkeypatch):
    """POST saves the finalized list AND propagates renames to topic_registry."""
    saved = {}
    renames = []
    async def fake_save(supabase, call_id, topics):
        saved["topics"] = topics
    async def fake_rename(supabase, topic_id, new_name):
        renames.append((topic_id, new_name))
    monkeypatch.setattr("backend.routers.topics.save_finalized_topics", fake_save)
    monkeypatch.setattr("backend.routers.topics.rename_topic_in_registry", fake_rename)

    payload = {
        "topics": [
            {"name": "ARM (renamed)", "source": "existing", "topic_id": "t1", "_original_name": "ARM"},
            {"name": "Stress Testing", "source": "new", "topic_id": None, "v5_cluster_id": "c1"},
        ]
    }
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post("/api/calls/call-uuid/topic-confirmation/save", json=payload)
    assert resp.status_code == 200
    assert len(saved["topics"]) == 2
    assert ("t1", "ARM (renamed)") in renames
```

- [ ] **Step 2: Implement**

```python
class TopicConfirmationPayload(BaseModel):
    topics: list[dict]  # each: {name, source, topic_id?, v5_cluster_id?, _original_name?}


@router.post("/api/calls/{call_id}/topic-confirmation/save")
async def save_topic_confirmation(
    call_id: str,
    payload: TopicConfirmationPayload,
    supabase = Depends(get_supabase),
):
    # Propagate renames to topic_registry (EPIC-20 decision #3: immediate propagation)
    for t in payload.topics:
        orig = t.get("_original_name")
        if orig and t.get("topic_id") and orig != t["name"]:
            await rename_topic_in_registry(supabase, t["topic_id"], t["name"])
    # Save finalized list
    clean = [
        {
            "name": t["name"],
            "source": t.get("source", "existing"),
            "topic_id": t.get("topic_id"),
            "v5_cluster_id": t.get("v5_cluster_id"),
        }
        for t in payload.topics
    ]
    await save_finalized_topics(supabase, call_id, clean)
    return {"ok": True, "count": len(clean)}


async def rename_topic_in_registry(supabase, topic_id: str, new_name: str) -> None:
    await supabase.table("topic_registry").update({"name": new_name}).eq("id", topic_id).execute()
```

- [ ] **Step 3: Test PASS, commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: POST /calls/{id}/topic-confirmation/save with rename propagation"
```

---

### Task 9: Frontend `TopicConfirmationStage` component

**Files:**
- Create: `frontend/src/components/TopicConfirmationStage.tsx`
- Create: `frontend/src/api/topicConfirmation.ts`

- [ ] **Step 1: API client wrapper**

```typescript
// frontend/src/api/topicConfirmation.ts
export type ExistingTopicEntry = { topic_id: string; name: string; tasks_count: number };
export type NewTopicCandidate = { name: string; v5_cluster_id: string | null; task_count: number };
export type FinalizedTopic = {
  id?: string;
  name: string;
  source: "existing" | "new";
  topic_id: string | null;
  v5_cluster_id?: string | null;
  _original_name?: string;
};

export const topicConfirmationAPI = {
  async load(callId: string) {
    const r = await fetch(`/api/calls/${callId}/topic-confirmation`);
    if (!r.ok) throw new Error("load failed");
    return r.json() as Promise<{
      existing: ExistingTopicEntry[];
      new_candidates: NewTopicCandidate[];
      finalized: FinalizedTopic[];
    }>;
  },
  async save(callId: string, topics: FinalizedTopic[]) {
    const r = await fetch(`/api/calls/${callId}/topic-confirmation/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topics }),
    });
    if (!r.ok) throw new Error("save failed");
    return r.json() as Promise<{ ok: true; count: number }>;
  },
};
```

- [ ] **Step 2: Stage 1 component skeleton (two-column layout)**

```typescript
// frontend/src/components/TopicConfirmationStage.tsx
import { useEffect, useState, useCallback } from "react";
import {
  topicConfirmationAPI,
  type ExistingTopicEntry,
  type NewTopicCandidate,
  type FinalizedTopic,
} from "@/api/topicConfirmation";

type Props = { callId: string; onAdvance: () => void };

export default function TopicConfirmationStage({ callId, onAdvance }: Props) {
  const [existing, setExisting] = useState<ExistingTopicEntry[]>([]);
  const [candidates, setCandidates] = useState<NewTopicCandidate[]>([]);
  const [finalized, setFinalized] = useState<FinalizedTopic[]>([]);
  const [busy, setBusy] = useState(false);

  // Initial load: if finalized empty, seed it with all existing topics (default: keep them all)
  useEffect(() => {
    topicConfirmationAPI.load(callId).then((d) => {
      setExisting(d.existing);
      setCandidates(d.new_candidates);
      if (d.finalized.length > 0) {
        setFinalized(d.finalized);
      } else {
        setFinalized([
          ...d.existing.map((t) => ({
            name: t.name,
            source: "existing" as const,
            topic_id: t.topic_id,
            _original_name: t.name,
          })),
        ]);
      }
    });
  }, [callId]);

  const isKept = (topicId: string) => finalized.some((f) => f.topic_id === topicId);
  const isAccepted = (name: string) => finalized.some((f) => f.source === "new" && f.name === name);

  const toggleExisting = (t: ExistingTopicEntry) => {
    if (isKept(t.topic_id)) {
      setFinalized((arr) => arr.filter((f) => f.topic_id !== t.topic_id));
    } else {
      setFinalized((arr) => [
        ...arr,
        { name: t.name, source: "existing", topic_id: t.topic_id, _original_name: t.name },
      ]);
    }
  };

  const toggleCandidate = (c: NewTopicCandidate) => {
    if (isAccepted(c.name)) {
      setFinalized((arr) => arr.filter((f) => !(f.source === "new" && f.name === c.name)));
    } else {
      setFinalized((arr) => [
        ...arr,
        { name: c.name, source: "new", topic_id: null, v5_cluster_id: c.v5_cluster_id },
      ]);
    }
  };

  const renameAt = (idx: number, newName: string) => {
    setFinalized((arr) => arr.map((f, i) => (i === idx ? { ...f, name: newName } : f)));
  };

  const introduceTopic = () => {
    const name = window.prompt("New topic name?");
    if (!name) return;
    setFinalized((arr) => [...arr, { name, source: "new", topic_id: null }]);
  };

  const save = useCallback(async () => {
    setBusy(true);
    try {
      await topicConfirmationAPI.save(callId, finalized);
      onAdvance();
    } finally {
      setBusy(false);
    }
  }, [callId, finalized, onAdvance]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
      <Column title={`Existing project topics (${existing.length})`}>
        {existing.map((t) => (
          <Row
            key={t.topic_id}
            label={`${t.name} (${t.tasks_count} tasks)`}
            checked={isKept(t.topic_id)}
            onToggle={() => toggleExisting(t)}
          />
        ))}
      </Column>
      <Column title={`New-topic candidates (${candidates.length})`}>
        {candidates.map((c) => (
          <Row
            key={c.name}
            label={`${c.name} (${c.task_count} tasks)`}
            checked={isAccepted(c.name)}
            onToggle={() => toggleCandidate(c)}
          />
        ))}
        <button onClick={introduceTopic} style={{ marginTop: 12 }}>+ Introduce topic</button>
      </Column>
      <Column title={`Finalized topic list (${finalized.length})`}>
        {finalized.map((f, i) => (
          <input
            key={`${f.source}-${f.topic_id ?? f.name}-${i}`}
            value={f.name}
            onChange={(e) => renameAt(i, e.target.value)}
            style={{ display: "block", width: "100%", marginBottom: 4 }}
          />
        ))}
        <button disabled={busy || finalized.length === 0} onClick={save} style={{ marginTop: 12 }}>
          {busy ? "Saving…" : "Save & advance"}
        </button>
      </Column>
    </div>
  );
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#f7f8fa", padding: 12, borderRadius: 6 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: () => void }) {
  return (
    <label style={{ display: "flex", gap: 6, marginBottom: 6 }}>
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <span>{label}</span>
    </label>
  );
}
```

- [ ] **Step 3: Mount in the call detail page**

In `frontend/app/projects/[id]/calls/[call_id]/page.tsx`, add a branch for `viewStage === "topic_confirmation"`:

```typescript
} else if (viewStage === "topic_confirmation") {
  return <TopicConfirmationStage callId={call.id} onAdvance={() => advanceStage()} />;
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: TopicConfirmationStage — two-column UI for Stage 1"
```

---

## Phase 3 — Stage 2 (Task grouping) refactor

### Task 10: Cluster+route LLM prompt

**Files:**
- Create: `backend/prompts/group_tasks.py`

- [ ] **Step 1: Write the prompt**

```python
# backend/prompts/group_tasks.py
"""EPIC-20 Stage 2: cluster tasks + propose target topic per group.

Input scope (kept narrow on purpose):
  - A fixed list of topics (the user's finalized topic list)
  - A list of tasks, each labeled as 'previous' (from prior calls) or 'new' (from this call)

Output:
  JSON array of groups. Each group:
    - task_ids: list of task identifiers from the input
    - target_topic: must be one of the topic names from the input (exact string match)
"""

GROUP_TASKS_SYSTEM = """\
You are clustering project tasks into small cohesive groups, then assigning each \
group to one topic from a fixed list.

Rules:
- A group contains tasks that describe the same workstream or sub-deliverable.
- Each group must have a target_topic chosen from the provided topic list. \
Use the topic name EXACTLY as listed.
- Tasks marked 'previous' are from prior calls; tasks marked 'new' are from \
the current call. Mix them in the same group when they describe the same \
workstream — that is the goal.
- Groups can be small (1-3 tasks) or larger (up to ~6). Prefer small + cohesive \
over large + fuzzy.
- Every input task must appear in exactly one group. No duplicates. No omissions.
- Do NOT introduce topics not in the list. Do NOT invent task IDs.

Return STRICT JSON:
[
  {"task_ids": ["..."], "target_topic": "..."},
  ...
]
"""


def build_group_tasks_user_message(
    topics: list[str],
    tasks: list[dict],
) -> str:
    lines = ["AVAILABLE TOPICS (pick exactly one per group):"]
    for t in topics:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("TASKS TO CLUSTER:")
    for t in tasks:
        origin = t.get("origin", "new")
        lines.append(f"- [{origin}] id={t['id']} :: {t['text']}")
    return "\n".join(lines)
```

- [ ] **Step 2: Commit (no test yet — tested as part of Task 11)**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: group_tasks LLM prompt"
```

---

### Task 11: Stage 2 LLM service (cluster + route)

**Files:**
- Create: `backend/services/task_grouping_service.py`
- Test: `backend/tests/test_task_grouping_service.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_task_grouping_service.py
import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest

from backend.services.task_grouping_service import run_task_grouping


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_groups_returned_match_input_topics(mock_llm):
    mock_llm.return_value = json.dumps([
        {"task_ids": ["t1", "t2"], "target_topic": "ARM"},
        {"task_ids": ["t3"], "target_topic": "Stress Testing"},
    ])
    topics = ["ARM", "Stress Testing"]
    tasks = [
        {"id": "t1", "text": "rebuild ARM models", "origin": "new"},
        {"id": "t2", "text": "validate ARM against last quarter", "origin": "previous"},
        {"id": "t3", "text": "stress test results", "origin": "new"},
    ]
    out = await run_task_grouping(topics, tasks, llm="openrouter", model="claude-sonnet-4-6")
    assert len(out["groups"]) == 2
    assert out["groups"][0]["target_topic"] == "ARM"
    assert out["unassigned"] == []  # all assigned


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_unassigned_tasks_go_to_orphan_bin(mock_llm):
    mock_llm.return_value = json.dumps([
        {"task_ids": ["t1"], "target_topic": "ARM"},
    ])
    out = await run_task_grouping(
        ["ARM"],
        [
            {"id": "t1", "text": "x", "origin": "new"},
            {"id": "t2", "text": "y", "origin": "new"},
        ],
        llm="openrouter", model="claude-sonnet-4-6",
    )
    assert out["unassigned"] == ["t2"]


@pytest.mark.asyncio
@patch("backend.services.task_grouping_service.call_llm_raw", new_callable=AsyncMock)
async def test_unknown_topic_is_rejected(mock_llm):
    mock_llm.return_value = json.dumps([
        {"task_ids": ["t1"], "target_topic": "Made-Up Topic"},
    ])
    out = await run_task_grouping(
        ["ARM"], [{"id": "t1", "text": "x", "origin": "new"}],
        llm="openrouter", model="claude-sonnet-4-6",
    )
    assert out["groups"] == []
    assert "Made-Up Topic" in out["rejected"][0]
    assert out["unassigned"] == ["t1"]
```

- [ ] **Step 2: Run, verify FAIL**

- [ ] **Step 3: Implement**

```python
# backend/services/task_grouping_service.py
"""EPIC-20 Stage 2: LLM cluster + route service."""
from __future__ import annotations

import json
import logging

from backend.prompts.group_tasks import (
    GROUP_TASKS_SYSTEM,
    build_group_tasks_user_message,
)
from backend.services.call_topics_v5.stage_2_atomic import _strip_code_fences
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.task_grouping")


async def run_task_grouping(
    topics: list[str],
    tasks: list[dict],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Cluster `tasks` into groups, each routed to one topic from `topics`.

    Returns dict with keys:
      - groups: list[{task_ids, target_topic}]
      - unassigned: list of task ids not placed in any group
      - rejected: validation reasons
    """
    if not tasks or not topics:
        return {"groups": [], "unassigned": [t["id"] for t in tasks], "rejected": []}

    user_msg = build_group_tasks_user_message(topics, tasks)
    logger.info("📥 task_grouping: %d topics, %d tasks", len(topics), len(tasks))
    raw = await call_llm_raw(
        GROUP_TASKS_SYSTEM, user_msg, llm,
        max_tokens=4096, model=model, temperature=0,
    )
    body = _strip_code_fences(raw)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("❌ task_grouping: invalid JSON: %s", e)
        return {"groups": [], "unassigned": [t["id"] for t in tasks], "rejected": [str(e)]}

    if not isinstance(parsed, list):
        return {"groups": [], "unassigned": [t["id"] for t in tasks], "rejected": ["not a list"]}

    valid_topics = set(topics)
    all_ids = {t["id"] for t in tasks}
    kept: list[dict] = []
    reasons: list[str] = []
    seen: set[str] = set()
    for i, g in enumerate(parsed):
        if not isinstance(g, dict):
            reasons.append(f"group {i}: not a dict")
            continue
        topic = (g.get("target_topic") or "").strip()
        if topic not in valid_topics:
            reasons.append(f"group {i}: unknown target_topic {topic!r}")
            continue
        ids = g.get("task_ids") or []
        ids = [x for x in ids if isinstance(x, str) and x in all_ids and x not in seen]
        if not ids:
            reasons.append(f"group {i}: no valid task_ids")
            continue
        seen.update(ids)
        kept.append({"task_ids": ids, "target_topic": topic})

    unassigned = sorted(all_ids - seen)
    logger.info("📤 task_grouping: %d groups, %d unassigned, %d rejected",
                len(kept), len(unassigned), len(reasons))
    return {"groups": kept, "unassigned": unassigned, "rejected": reasons}
```

- [ ] **Step 4: Test PASS**

```bash
pytest backend/tests/test_task_grouping_service.py -v
```

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: task_grouping_service — LLM cluster+route"
```

---

### Task 12: Endpoint to trigger task grouping for a call

**Files:**
- Modify: `backend/routers/topics.py`

- [ ] **Step 1: Add the endpoint**

```python
@router.post("/api/calls/{call_id}/task-grouping/run")
async def run_task_grouping_endpoint(
    call_id: str,
    supabase = Depends(get_supabase),
):
    """Run Stage 2 LLM grouping. Builds the input from:
      - Finalized topics for this call
      - All tasks: previous-call tasks for each kept topic + v5 atomic tasks
    Persists the resulting groups as draft topic_match_groups.
    """
    # 1. Load finalized topics
    finalized = await load_finalized_topics(supabase, call_id)
    if not finalized:
        raise HTTPException(400, "no finalized topics — complete Stage 1 first")
    topic_names = [t["name"] for t in finalized]
    ft_by_name = {t["name"]: t["id"] for t in finalized}

    # 2. Collect previous-call tasks (one bag per kept topic; EPIC-20 decision #1)
    prev_tasks: list[dict] = []
    for ft in finalized:
        if ft["source"] != "existing" or not ft.get("topic_id"):
            continue
        state = await (
            supabase.table("project_topic_state")
            .select("tasks")
            .eq("topic_id", ft["topic_id"])
            .single()
            .execute()
        )
        for pt in (state.data or {}).get("tasks", []) or []:
            if pt.get("task_id"):
                prev_tasks.append({
                    "id": f"prev:{pt['task_id']}",
                    "text": pt.get("task", ""),
                    "origin": "previous",
                    "_topic_name": ft["name"],
                    "_task_id": pt["task_id"],
                    "_topic_id": ft["topic_id"],
                })

    # 3. Collect new-call atomic tasks (v5 Stage 4 output)
    call_resp = await supabase.table("calls").select("call_topics_v5").eq("id", call_id).single().execute()
    v5 = (call_resp.data or {}).get("call_topics_v5") or {}
    new_tasks = []
    for u in v5.get("atomic_units", []) or []:
        if u.get("type") != "task":
            continue
        new_tasks.append({
            "id": f"new:{u['unit_id']}",
            "text": u.get("text", ""),
            "origin": "new",
            "_unit_id": u["unit_id"],
        })

    # 4. Run LLM
    result = await run_task_grouping(
        topic_names,
        prev_tasks + new_tasks,
        llm="openrouter",
        model="anthropic/claude-sonnet-4-6",
    )

    # 5. Persist as draft groups + return shape
    groups_to_save: list[TaskMatchGroup] = []
    tasks_by_id = {t["id"]: t for t in prev_tasks + new_tasks}
    for g in result["groups"]:
        ftid = ft_by_name[g["target_topic"]]
        call_refs, proj_refs = [], []
        for tid in g["task_ids"]:
            t = tasks_by_id[tid]
            if t["origin"] == "new":
                call_refs.append({"task_id": t["_unit_id"]})
            else:
                proj_refs.append({"project_topic_id": t["_topic_id"], "task_id": t["_task_id"]})
        kind = "mixed" if (call_refs and proj_refs) else ("new_only" if call_refs else "old_only")
        groups_to_save.append({
            "finalized_topic_id": ftid,
            "group_kind": kind,
            "call_task_refs": call_refs,
            "project_task_refs": proj_refs,
        })
    await save_task_match_groups(supabase, call_id, groups_to_save, draft=True)

    return {
        "groups": groups_to_save,
        "unassigned": result["unassigned"],
        "rejected": result["rejected"],
    }
```

- [ ] **Step 2: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: POST /calls/{id}/task-grouping/run — Stage 2 LLM trigger"
```

---

### Task 13: Frontend `TaskGroupingStage` component

**Files:**
- Create: `frontend/src/components/TaskGroupingStage.tsx`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

- [ ] **Step 1: Component skeleton**

```typescript
// frontend/src/components/TaskGroupingStage.tsx
import { useEffect, useState, useCallback, useMemo } from "react";
import { topicsAPI } from "@/api/topics";

type Task = { id: string; text: string; origin: "new" | "previous" };
type Group = {
  id: string;
  finalized_topic_id: string;
  group_kind: "new_only" | "old_only" | "mixed";
  task_ids: string[];  // local IDs (prefixed `new:` or `prev:`)
};
type Topic = { id: string; name: string };

type Props = { callId: string; onAdvance: () => void };

export default function TaskGroupingStage({ callId, onAdvance }: Props) {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [orphans, setOrphans] = useState<string[]>([]);
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);
  const [dragGroupId, setDragGroupId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Initial load — fetch finalized topics + existing groups + atomic tasks
  useEffect(() => { reload(); }, [callId]);

  const reload = async () => {
    const d = await topicsAPI.loadTaskGroupingState(callId);
    setTopics(d.topics);
    setTasks(d.tasks);
    setGroups(d.groups);
    setOrphans(d.orphans);
  };

  const runLLM = async () => {
    setBusy(true);
    try {
      await topicsAPI.runTaskGrouping(callId);
      await reload();
    } finally {
      setBusy(false);
    }
  };

  const groupsByTopic = useMemo(() => {
    const m = new Map<string, Group[]>();
    for (const t of topics) m.set(t.id, []);
    for (const g of groups) {
      m.get(g.finalized_topic_id)?.push(g);
    }
    return m;
  }, [topics, groups]);

  // === Drag handlers ===

  const onTaskDragStart = (e: React.DragEvent, taskId: string) => {
    setDragTaskId(taskId);
    e.dataTransfer.setData("text/plain", `task:${taskId}`);
    e.dataTransfer.effectAllowed = "move";
  };

  const onGroupDragStart = (e: React.DragEvent, gid: string) => {
    setDragGroupId(gid);
    e.dataTransfer.setData("text/plain", `group:${gid}`);
    e.dataTransfer.effectAllowed = "move";
  };

  const onDropOnGroup = (e: React.DragEvent, targetGroupId: string) => {
    e.preventDefault();
    const payload = e.dataTransfer.getData("text/plain");
    if (payload.startsWith("task:")) {
      const taskId = payload.slice(5);
      // Remove from current group / orphans, add to target group
      setGroups((arr) =>
        arr.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) }))
          .map((g) => g.id === targetGroupId ? { ...g, task_ids: [...g.task_ids, taskId] } : g)
      );
      setOrphans((arr) => arr.filter((tid) => tid !== taskId));
    }
    setDragTaskId(null);
    setDragGroupId(null);
  };

  const onDropOnTopic = (e: React.DragEvent, topicId: string) => {
    e.preventDefault();
    const payload = e.dataTransfer.getData("text/plain");
    if (payload.startsWith("group:")) {
      const gid = payload.slice(6);
      setGroups((arr) => arr.map((g) => g.id === gid ? { ...g, finalized_topic_id: topicId } : g));
    } else if (payload.startsWith("task:")) {
      // Drop on topic column (not on a specific group) → create a NEW group under this topic
      const taskId = payload.slice(5);
      const newId = crypto.randomUUID();
      setGroups((arr) => [
        ...arr.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) })),
        {
          id: newId,
          finalized_topic_id: topicId,
          group_kind: taskId.startsWith("new:") ? "new_only" : "old_only",
          task_ids: [taskId],
        },
      ]);
      setOrphans((arr) => arr.filter((tid) => tid !== taskId));
    }
    setDragTaskId(null);
    setDragGroupId(null);
  };

  // === Advance gate ===
  const canAdvance = orphans.length === 0 && groups.length > 0;

  const save = useCallback(async () => {
    await topicsAPI.saveTaskGroups(callId, groups);
    onAdvance();
  }, [callId, groups, onAdvance]);

  // Auto-save on changes (debounced)
  useEffect(() => {
    const t = setTimeout(() => {
      topicsAPI.saveTaskGroups(callId, groups).catch(() => {});
    }, 500);
    return () => clearTimeout(t);
  }, [callId, groups]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <h2>Task grouping</h2>
        <div>
          <button onClick={runLLM} disabled={busy}>{busy ? "Clustering…" : "Re-cluster (LLM)"}</button>
          <button onClick={save} disabled={!canAdvance} style={{ marginLeft: 8 }}>Advance to Stage 3</button>
        </div>
      </div>
      {orphans.length > 0 && (
        <OrphanBin
          orphans={orphans.map((id) => tasks.find((t) => t.id === id)!)}
          onTaskDragStart={onTaskDragStart}
        />
      )}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${topics.length}, 1fr)`, gap: 12, marginTop: 12 }}>
        {topics.map((t) => (
          <TopicColumn
            key={t.id}
            topic={t}
            groups={groupsByTopic.get(t.id) ?? []}
            tasks={tasks}
            onTaskDragStart={onTaskDragStart}
            onGroupDragStart={onGroupDragStart}
            onDropOnGroup={onDropOnGroup}
            onDropOnTopic={(e) => onDropOnTopic(e, t.id)}
            isDropTarget={dragGroupId !== null || dragTaskId !== null}
          />
        ))}
      </div>
    </div>
  );
}

// Sub-components: OrphanBin, TopicColumn, GroupCard, TaskPill
// (Standard React patterns; full code in task body)
```

- [ ] **Step 2: Sub-components**

```typescript
function OrphanBin({ orphans, onTaskDragStart }: {
  orphans: Task[];
  onTaskDragStart: (e: React.DragEvent, taskId: string) => void;
}) {
  return (
    <div style={{ background: "#fff3cd", border: "2px dashed #ffa", padding: 12, borderRadius: 6 }}>
      <h3 style={{ marginTop: 0 }}>Ungrouped ({orphans.length}) — drag into a group or topic before advancing</h3>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {orphans.map((t) => (
          <TaskPill key={t.id} task={t} onDragStart={(e) => onTaskDragStart(e, t.id)} />
        ))}
      </div>
    </div>
  );
}

function TopicColumn({ topic, groups, tasks, onTaskDragStart, onGroupDragStart, onDropOnGroup, onDropOnTopic, isDropTarget }: {
  topic: Topic;
  groups: Group[];
  tasks: Task[];
  onTaskDragStart: (e: React.DragEvent, taskId: string) => void;
  onGroupDragStart: (e: React.DragEvent, gid: string) => void;
  onDropOnGroup: (e: React.DragEvent, gid: string) => void;
  onDropOnTopic: (e: React.DragEvent) => void;
  isDropTarget: boolean;
}) {
  return (
    <div
      onDragOver={(e) => isDropTarget && e.preventDefault()}
      onDrop={onDropOnTopic}
      style={{ background: "#f7f8fa", padding: 12, borderRadius: 6, minHeight: 200 }}
    >
      <h4>{topic.name}</h4>
      {groups.map((g) => (
        <GroupCard key={g.id} group={g} tasks={tasks}
          onTaskDragStart={onTaskDragStart}
          onGroupDragStart={onGroupDragStart}
          onDropOnGroup={onDropOnGroup}
        />
      ))}
    </div>
  );
}

function GroupCard({ group, tasks, onTaskDragStart, onGroupDragStart, onDropOnGroup }: {
  group: Group; tasks: Task[];
  onTaskDragStart: (e: React.DragEvent, taskId: string) => void;
  onGroupDragStart: (e: React.DragEvent, gid: string) => void;
  onDropOnGroup: (e: React.DragEvent, gid: string) => void;
}) {
  const kindColor = { new_only: "#d4f0d4", old_only: "#ffd6cc", mixed: "#ffe5b3" }[group.group_kind];
  return (
    <div
      draggable
      onDragStart={(e) => onGroupDragStart(e, group.id)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => onDropOnGroup(e, group.id)}
      style={{ background: kindColor, padding: 6, marginBottom: 6, borderRadius: 4, cursor: "grab" }}
    >
      {group.task_ids.map((tid) => {
        const t = tasks.find((x) => x.id === tid);
        return t ? <TaskPill key={tid} task={t} onDragStart={(e) => onTaskDragStart(e, tid)} /> : null;
      })}
    </div>
  );
}

function TaskPill({ task, onDragStart }: { task: Task; onDragStart: (e: React.DragEvent) => void }) {
  const bg = task.origin === "new" ? "#cce5ff" : "#e6e6e6";
  return (
    <div
      draggable
      onDragStart={onDragStart}
      style={{ background: bg, padding: "4px 8px", margin: 2, borderRadius: 12, cursor: "grab", fontSize: 12, display: "inline-block" }}
      title={task.text}
    >
      {task.text.slice(0, 60)}{task.text.length > 60 ? "…" : ""}
    </div>
  );
}
```

- [ ] **Step 3: API methods (topicsAPI)**

Add to `frontend/src/api/topics.ts`:

```typescript
async loadTaskGroupingState(callId: string) {
  const r = await fetch(`/api/calls/${callId}/task-grouping/state`);
  return r.json() as Promise<{
    topics: { id: string; name: string }[];
    tasks: { id: string; text: string; origin: "new" | "previous" }[];
    groups: Array<{
      id: string;
      finalized_topic_id: string;
      group_kind: "new_only" | "old_only" | "mixed";
      task_ids: string[];
    }>;
    orphans: string[];
  }>;
},
async runTaskGrouping(callId: string) {
  await fetch(`/api/calls/${callId}/task-grouping/run`, { method: "POST" });
},
async saveTaskGroups(callId: string, groups: Group[]) {
  await fetch(`/api/calls/${callId}/task-grouping/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groups }),
  });
},
```

- [ ] **Step 4: Wire the stage in page.tsx**

```typescript
} else if (viewStage === "task_grouping") {  // renamed from project_matching
  return <TaskGroupingStage callId={call.id} onAdvance={() => advanceStage()} />;
}
```

- [ ] **Step 5: TypeScript check + commit**

```bash
cd frontend && npx tsc --noEmit
python3 scripts/git_ops.py commit "[EPIC-20] feat: TaskGroupingStage — drag/drop UI with orphan bin"
```

---

### Task 14: Backend endpoints for grouping state + save

**Files:**
- Modify: `backend/routers/topics.py`

- [ ] **Step 1: Add `GET /task-grouping/state` and `POST /task-grouping/save`**

```python
@router.get("/api/calls/{call_id}/task-grouping/state")
async def get_task_grouping_state(call_id: str, supabase = Depends(get_supabase)):
    finalized = await load_finalized_topics(supabase, call_id)
    topics_out = [{"id": t["id"], "name": t["name"]} for t in finalized]
    ft_by_name = {t["name"]: t["id"] for t in finalized}

    # Build the same task list as `run_task_grouping_endpoint`
    prev_tasks, new_tasks = await _collect_tasks_for_grouping(supabase, call_id, finalized)
    all_tasks = prev_tasks + new_tasks
    tasks_out = [{"id": t["id"], "text": t["text"], "origin": t["origin"]} for t in all_tasks]

    # Existing groups → convert to local task-id format
    groups_db = await load_task_match_groups(supabase, call_id)
    groups_out, assigned_ids = [], set()
    for g in groups_db:
        task_ids = []
        for r in (g.get("call_task_refs") or []):
            task_ids.append(f"new:{r['task_id']}")
        for r in (g.get("project_task_refs") or []):
            task_ids.append(f"prev:{r['task_id']}")
        assigned_ids.update(task_ids)
        groups_out.append({
            "id": g["id"],
            "finalized_topic_id": g.get("finalized_topic_id"),
            "group_kind": g.get("group_kind") or "new_only",
            "task_ids": task_ids,
        })
    orphans = [t["id"] for t in all_tasks if t["id"] not in assigned_ids]
    return {"topics": topics_out, "tasks": tasks_out, "groups": groups_out, "orphans": orphans}


async def _collect_tasks_for_grouping(supabase, call_id, finalized):
    """Shared helper: previous-call tasks + v5 atomic tasks."""
    # ... same logic as in run_task_grouping_endpoint, Steps 2+3 ...
    # Returns (prev_tasks, new_tasks)


class TaskGroupingSavePayload(BaseModel):
    groups: list[dict]  # {id, finalized_topic_id, group_kind, task_ids}


@router.post("/api/calls/{call_id}/task-grouping/save")
async def save_task_grouping(
    call_id: str,
    payload: TaskGroupingSavePayload,
    supabase = Depends(get_supabase),
):
    # Convert task_ids (prefixed) back to call_task_refs + project_task_refs
    finalized = await load_finalized_topics(supabase, call_id)
    prev_tasks, new_tasks = await _collect_tasks_for_grouping(supabase, call_id, finalized)
    tasks_by_id = {t["id"]: t for t in prev_tasks + new_tasks}

    groups_to_save: list[TaskMatchGroup] = []
    for g in payload.groups:
        call_refs, proj_refs = [], []
        for tid in g.get("task_ids", []):
            t = tasks_by_id.get(tid)
            if not t:
                continue
            if t["origin"] == "new":
                call_refs.append({"task_id": t["_unit_id"]})
            else:
                proj_refs.append({"project_topic_id": t["_topic_id"], "task_id": t["_task_id"]})
        kind = "mixed" if (call_refs and proj_refs) else ("new_only" if call_refs else "old_only")
        groups_to_save.append({
            "id": g.get("id"),
            "finalized_topic_id": g["finalized_topic_id"],
            "group_kind": kind,
            "call_task_refs": call_refs,
            "project_task_refs": proj_refs,
        })
    await save_task_match_groups(supabase, call_id, groups_to_save, draft=True)
    return {"ok": True, "count": len(groups_to_save)}
```

- [ ] **Step 2: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: task-grouping state + save endpoints"
```

---

## Phase 4 — Stage 3 wiring + cleanup

### Task 15: Route 3 passes by `group_kind`

**Files:**
- Modify: `backend/routers/topics.py` (the Pass 1/2/3 trigger endpoints)

- [ ] **Step 1: Update each Pass trigger to filter by group_kind**

Pass 1 trigger:
```python
# Was: iterate over X:0 groups (or kind == "binding" with no project_task_refs)
# Now:
x_groups = [g for g in groups if g.get("group_kind") == "new_only"]
```

Pass 2 trigger:
```python
# Was: iterate over notInCall topics OR 0:X groups
# Now:
o_groups = [g for g in groups if g.get("group_kind") == "old_only"]
```

Pass 3 trigger:
```python
# Was: iterate over mergedBindingGroups grouped by primary_target
# Now: iterate over mixed groups directly
m_groups = [g for g in groups if g.get("group_kind") == "mixed"]
```

- [ ] **Step 2: Run smoke (assumes mocked LLM in tests; manual smoke comes in Task 17)**

```bash
pytest backend/tests/ -k "pass" -v
```

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] feat: route 3 passes by group_kind"
```

---

### Task 16: Delete EPIC-19 multi-topic primary-target plumbing

**Files:**
- Modify: `frontend/src/components/ProjectUpdatesStage.tsx` (or its replacement)

- [ ] **Step 1: Remove dead code**

Targets to delete:
- The `primaryTopicForGroup` helper
- The `secondaryTopicNames` annotation
- Drag-onto-section-2 handlers (now native to Stage 2's drag UX)
- Drag-onto-section-3 handlers (same)
- "Accept merge" button logic (replaced by drag in Stage 2)
- `mergedByTopic` sub-group collapsing (one group per topic by construction now)

What remains in ProjectUpdatesStage:
- Three sections (Section 1 = new_only groups for Pass 1; Section 2 = old_only for Pass 2; Section 3 = mixed for Pass 3)
- Per-group verdict cards
- Pass triggers

- [ ] **Step 2: Verify no broken imports**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] chore: delete EPIC-19 multi-topic primary-target plumbing"
```

---

### Task 17: Smoke test against project a + project b

**Files:** none (manual operation)

- [ ] **Step 1: Verify migrations 037 + 038 are applied**

```sql
-- In Supabase SQL editor:
select count(*) from call_finalized_topics;
select column_name from information_schema.columns
  where table_name = 'topic_match_groups' and column_name in ('finalized_topic_id', 'group_kind');
```

- [ ] **Step 2: Run backfill**

```bash
python3 backend/scripts/backfill_finalized_topics.py
```

Expected: `✅ call ...: backfilled N topics, M groups` for each call.

- [ ] **Step 3: Smoke project a (existing call)**

In browser:
1. Open project a → an existing follow-up call
2. Advance to `topic_confirmation` stage (or back-navigate if already advanced)
3. Confirm finalized topic list shows existing topics + v5 candidates
4. Edit, save → advance
5. On `task_grouping`, click "Re-cluster (LLM)"
6. Observe: orphan bin, topic columns, color-coded groups
7. Drag tasks between groups; drag groups between topics
8. Save & advance to `project_updates`
9. Verify Pass 1 fires only on new_only groups, Pass 2 on old_only, Pass 3 on mixed
10. Note any UX issues or LLM-output anomalies

- [ ] **Step 4: Smoke project b (fresh call upload)**

Repeat from raw upload through artifacts. Document issues.

- [ ] **Step 5: Commit any fixes that came up during smoke**

---

### Task 18: Documentation updates

**Files:**
- Modify: `docs/project/config/codebase.md`
- Modify: `docs/project/config/build-log.md`
- Modify: `workflow/ADR.md`

- [ ] **Step 1: Codebase map**

Add entries:
- `backend/services/finalized_topics_service.py` — Stage 1 CRUD
- `backend/services/task_grouping_service.py` — Stage 2 LLM cluster+route
- `backend/prompts/group_tasks.py` — Stage 2 prompt
- `frontend/src/components/TopicConfirmationStage.tsx`
- `frontend/src/components/TaskGroupingStage.tsx`

Remove entries that no longer exist (deleted EPIC-19 plumbing).

- [ ] **Step 2: ADR entry**

```markdown
## ADR-005 (2026-05-27): Three-stage call processing

**Decision:** Split call processing into Stage 1 (Topic confirmation) → Stage 2 (Task grouping) → Stage 3 (Project updates).

**Context:** EPIC-19's single-screen N:M matching was slow and tangled three decisions (topic lifecycle, task grouping, task binding) into one UX. The LLM had no constraint reduction.

**Consequence:** Stage 1 produces a finalized topic list (user-driven). Stage 2 LLM cluster+route runs against that fixed list (narrow scope, deterministic enum). Stage 3 routes the 3 existing passes by group_kind. Groups are 1:1 with topics by construction — kills the multi-target primary-target hack.

**Trade-off:** One extra kanban stage to traverse. Mitigated by inline-edit at Stage 2 and the "Re-cluster" affordance.
```

- [ ] **Step 3: Build log entry**

Update `build-log.md` with EPIC-20 completion + smoke results from Task 17.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-20] docs: codebase, ADR-005, build-log updates"
```

---

## Manual steps for the user (surface at end of execution)

1. **Run migration 037** (`call_finalized_topics` table) in Supabase Dashboard
2. **Run migration 038** (`topic_match_groups` simplification) in Supabase Dashboard
3. **Run `notify pgrst, 'reload schema';`** in Supabase SQL editor (PostgREST cache)
4. **Run backfill script:** `python3 backend/scripts/backfill_finalized_topics.py`
5. **Smoke test** in browser per Task 17

---

## Self-review

**Spec coverage:**
- ✅ Stage 1 topic confirmation (Tasks 6-9)
- ✅ Stage 2 LLM cluster+route (Tasks 10-14)
- ✅ Stage 3 pass routing by group_kind (Task 15)
- ✅ EPIC-19 cleanup (Task 16)
- ✅ Smoke + docs (Tasks 17-18)
- ✅ Data model + migrations (Tasks 1-5)
- ✅ All 6 locked decisions surfaced in tasks (one-bag old-only in Task 12; global LLM scope in Task 11; rename propagation in Task 8; re-cluster button in Task 13; immediate draft persistence in Task 12; two-column UI in Task 9)

**Type consistency:**
- `FinalizedTopic` shape consistent across Tasks 3, 7, 8, 9
- `TaskMatchGroup` shape consistent across Tasks 4, 12, 14
- Frontend `Group` / `Task` / `Topic` types consistent in Task 13

**Placeholder scan:** No "TBD" / "implement later". All steps have full code or full command. The `_collect_tasks_for_grouping` helper in Task 14 references logic from Task 12 — engineer extracts the shared bit; both tasks show the full logic.

---

## Execution handoff

Use `superpowers:subagent-driven-development` for task-by-task execution. After each task:
- Implementer commits
- Self-verify via test output + commit log
- Move to next task (no human-in-loop until Task 17 smoke)

User check-in points:
- After Task 5 (migrations + backfill ready — surface manual SQL steps)
- After Task 9 (Stage 1 UI ready — visual review before continuing)
- After Task 13 (Stage 2 UI ready — visual review)
- After Task 17 (smoke complete — final review)
