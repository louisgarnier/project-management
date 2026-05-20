# Topics Timeline — Pending Topics Support

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Topics tab timeline show raw (unmerged) call topics for calls that have no committed `topic_updates`, so the matrix never goes blank after a rollback.

**Architecture:** `list_topics_timeline` currently reads only from the `topics` + `topic_updates` tables. We extend it to also read `extraction_cache` / `pending_topics` from the `calls` table for calls that have no committed `topic_updates`. Those raw topics are appended to the result with synthetic IDs (`"pending:<call_id>:<index>"`) and a new cell type `"pending"`. The frontend renders `"pending"` cells with a distinct style. No DB schema changes needed.

**Tech Stack:** Python/FastAPI backend (`topics_service.py`), TypeScript/React frontend (`types/index.ts`, `TopicsTimeline.tsx`), pytest, Jest/RTL not needed (visual change only for frontend).

---

## File Map

| File | Change |
|---|---|
| `backend/services/topics_service.py` | Extend `list_topics_timeline` to inject pending topic rows |
| `backend/tests/test_topics.py` | Add test for pending topic rows in timeline |
| `frontend/src/types/index.ts` | Add `"pending"` to `TimelineCell.type` |
| `frontend/src/components/TopicsTimeline.tsx` | Render `"pending"` cell type |

---

## Task 1: Backend — inject pending rows into `list_topics_timeline`

**Files:**
- Modify: `backend/services/topics_service.py` (function `list_topics_timeline`, lines 1128–1269)

**Context on current shape:**

`list_topics_timeline` returns:
```python
{
  "calls": [{"id", "title", "call_number", "kanban_stage"}, ...],
  "topics": [{
    "topic_id": str,           # UUID from topics table
    "name": str,
    "status": str,
    "owner": str,
    "sentiment": str,
    "first_raised_call_id": str | None,
    "call_updates": {
      "<call_id>": {
        "type": "new" | "followed_up" | "not_discussed",
        "summary": str, ...
      }
    }
  }, ...]
}
```

For calls with no `topic_updates`, we append synthetic rows with:
- `topic_id`: `f"pending:{call_id}:{i}"` (not a UUID — frontend must handle)
- `call_updates`: only one key (the call's own ID), type `"pending"`
- No `"not_discussed"` entries for other calls

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_topics.py`, add after the existing timeline tests:

```python
def test_timeline_shows_pending_topics_for_calls_without_updates(client, mock_db):
    """Calls at call_topics stage with extraction_cache but no topic_updates
    appear in the timeline as pending rows."""
    project_id = "proj-1"
    call_id = "call-1"

    mock_db["calls"] = [
        {
            "id": call_id,
            "title": "C1",
            "kanban_stage": "call_topics",
            "created_at": "2026-01-01T00:00:00Z",
            "extraction_cache": [
                {
                    "name": "Risk Model",
                    "summary": "Discussed risk",
                    "follow_up_items": [],
                    "decisions": [],
                    "status": "open",
                    "owner": "Us",
                    "sentiment": "neutral",
                }
            ],
            "pending_topics": None,
        }
    ]
    mock_db["topics"] = []
    mock_db["topic_updates"] = []

    result = list_topics_timeline(project_id)

    assert len(result["calls"]) == 1
    assert len(result["topics"]) == 1
    row = result["topics"][0]
    assert row["topic_id"].startswith("pending:")
    assert row["name"] == "Risk Model"
    assert call_id in row["call_updates"]
    assert row["call_updates"][call_id]["type"] == "pending"
    assert row["call_updates"][call_id]["summary"] == "Discussed risk"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::test_timeline_shows_pending_topics_for_calls_without_updates -v
```

Expected: FAIL (pending rows not returned yet)

- [ ] **Step 3: Implement the change in `list_topics_timeline`**

In `backend/services/topics_service.py`, replace the `return {"calls": all_calls, "topics": result_topics}` at the end of `list_topics_timeline` with:

```python
    # ── Pending rows for calls with no committed topic_updates ──────────────
    # Collect which call_ids have at least one topic_update in this timeline
    calls_with_updates: set[str] = {u["call_id"] for u in updates}

    calls_without_updates = [c for c in all_calls if c["id"] not in calls_with_updates]

    if calls_without_updates:
        raw_ids = [c["id"] for c in calls_without_updates]
        raw_rows = (
            db.table("calls")
            .select("id, pending_topics, extraction_cache")
            .in_("id", raw_ids)
            .execute()
            .data
        )
        for row in raw_rows:
            cid = row["id"]
            raw_topics = row.get("pending_topics") or row.get("extraction_cache") or []
            for i, rt in enumerate(raw_topics):
                result_topics.append({
                    "topic_id": f"pending:{cid}:{i}",
                    "name": rt.get("name", ""),
                    "status": rt.get("status", "open"),
                    "owner": rt.get("owner", "Us"),
                    "sentiment": rt.get("sentiment", "neutral"),
                    "first_raised_call_id": cid,
                    "call_updates": {
                        cid: {
                            "type": "pending",
                            "summary": rt.get("summary", ""),
                            "follow_up_items": rt.get("follow_up_items") or [],
                            "decisions": rt.get("decisions") or [],
                            "status": rt.get("status", "open"),
                            "owner": rt.get("owner", "Us"),
                            "sentiment": rt.get("sentiment", "neutral"),
                        }
                    },
                })

    return {"calls": all_calls, "topics": result_topics}
```

Also update the early-exit guard at line ~1190 to not return early just because `topics` is empty (pending rows may still exist):

Replace:
```python
    if not topics:
        return {"calls": all_calls, "topics": []}
```

With:
```python
    if not topics:
        topic_ids = []
```

And adjust the `if not topic_ids:` guard on `latest_updates` similarly (already done via `if topic_ids else []`).

The full updated tail of the function (from `topic_ids = ...` through the return):

```python
    topic_ids = [t["id"] for t in topics]

    updates = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, follow_up_items, decisions, status, owner, sentiment")
        .in_("topic_id", topic_ids)
        .in_("call_id", call_ids)
        .execute()
        .data
    ) if topic_ids else []
    updates_index: dict[str, dict[str, dict]] = {}
    for u in updates:
        tid = u["topic_id"]
        cid = u["call_id"]
        if tid not in updates_index:
            updates_index[tid] = {}
        updates_index[tid][cid] = u

    latest_updates = (
        db.table("topic_updates")
        .select("topic_id, status, owner, sentiment, created_at")
        .in_("topic_id", topic_ids)
        .order("created_at", desc=True)
        .execute()
        .data
    ) if topic_ids else []
    latest_state: dict = {}
    for u in latest_updates:
        tid = u["topic_id"]
        if tid not in latest_state:
            latest_state[tid] = u

    result_topics = []
    for t in topics:
        tid = t["id"]
        first_call_id = t.get("first_raised_call_id")
        first_idx = call_order.get(first_call_id, 0) if first_call_id else 0
        topic_updates_by_call = updates_index.get(tid, {})

        call_updates: dict[str, dict] = {}
        for c in all_calls:
            cid = c["id"]
            cidx = call_order[cid]
            if cidx < first_idx:
                continue
            if cid in topic_updates_by_call:
                u = topic_updates_by_call[cid]
                cell_type = "new" if cid == first_call_id else "followed_up"
                call_updates[cid] = {
                    "type": cell_type,
                    "summary": u.get("summary", ""),
                    "follow_up_items": u.get("follow_up_items") or [],
                    "decisions": u.get("decisions") or [],
                    "status": u.get("status", "open"),
                    "owner": u.get("owner", "Us"),
                    "sentiment": u.get("sentiment", "neutral"),
                }
            else:
                call_updates[cid] = {"type": "not_discussed"}

        ls = latest_state.get(tid, {})
        result_topics.append({
            "topic_id": tid,
            "name": t["name"],
            "status": ls.get("status", "open"),
            "owner": ls.get("owner", "Us"),
            "sentiment": ls.get("sentiment", "neutral"),
            "first_raised_call_id": first_call_id,
            "call_updates": call_updates,
        })

    # ── Pending rows for calls with no committed topic_updates ──────────────
    calls_with_updates: set[str] = {u["call_id"] for u in updates}
    calls_without_updates = [c for c in all_calls if c["id"] not in calls_with_updates]

    if calls_without_updates:
        raw_ids = [c["id"] for c in calls_without_updates]
        raw_rows = (
            db.table("calls")
            .select("id, pending_topics, extraction_cache")
            .in_("id", raw_ids)
            .execute()
            .data
        )
        for row in raw_rows:
            cid = row["id"]
            raw_topics = row.get("pending_topics") or row.get("extraction_cache") or []
            for i, rt in enumerate(raw_topics):
                result_topics.append({
                    "topic_id": f"pending:{cid}:{i}",
                    "name": rt.get("name", ""),
                    "status": rt.get("status", "open"),
                    "owner": rt.get("owner", "Us"),
                    "sentiment": rt.get("sentiment", "neutral"),
                    "first_raised_call_id": cid,
                    "call_updates": {
                        cid: {
                            "type": "pending",
                            "summary": rt.get("summary", ""),
                            "follow_up_items": rt.get("follow_up_items") or [],
                            "decisions": rt.get("decisions") or [],
                            "status": rt.get("status", "open"),
                            "owner": rt.get("owner", "Us"),
                            "sentiment": rt.get("sentiment", "neutral"),
                        }
                    },
                })

    return {"calls": all_calls, "topics": result_topics}
```

- [ ] **Step 4: Run the test again to confirm it passes**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::test_timeline_shows_pending_topics_for_calls_without_updates -v
```

Expected: PASS

- [ ] **Step 5: Run full backend test suite**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: topics timeline shows pending rows for calls without topic_updates"
```

---

## Task 2: Frontend — add `"pending"` cell type

**Files:**
- Modify: `frontend/src/types/index.ts` (line ~144)
- Modify: `frontend/src/components/TopicsTimeline.tsx` (Cell component, lines ~30–110)

- [ ] **Step 1: Update `TimelineCell` type**

In `frontend/src/types/index.ts`, change:

```typescript
export interface TimelineCell {
  type: "new" | "followed_up" | "not_discussed";
```

To:

```typescript
export interface TimelineCell {
  type: "new" | "followed_up" | "not_discussed" | "pending";
```

- [ ] **Step 2: Update `Cell` component in `TopicsTimeline.tsx`**

In `frontend/src/components/TopicsTimeline.tsx`, in the `Cell` function, add a `"pending"` branch after the `"not_discussed"` check:

```typescript
  if (cell.type === "not_discussed") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", textAlign: "center", color: "#bfc5ce",
        fontSize: 13, paddingTop: 14 }}>
        —
      </td>
    );
  }

  if (cell.type === "pending") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", padding: "6px 8px" }}>
        <div style={{
          border: "1.5px dashed #c0c8d8",
          borderRadius: 5,
          padding: "7px 9px",
          background: "#fafbfc",
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#97a0af",
            textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 4 }}>
            Extracted
          </div>
          {cell.summary && (
            <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>
              {cell.summary}
            </div>
          )}
        </div>
      </td>
    );
  }
```

- [ ] **Step 3: Check TypeScript compiles cleanly**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Check ESLint passes**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx eslint src/types/index.ts src/components/TopicsTimeline.tsx
```

Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: render pending cell type in topics timeline"
```

---

## Self-Review

**Spec coverage:**
- ✅ Calls at call_topics with extraction_cache → pending rows in timeline
- ✅ Calls with committed topic_updates → unchanged behavior
- ✅ Pending rows only appear in their own call's column (no not_discussed for other calls)
- ✅ After project_updates runs → those topics become real rows (committed), pending rows disappear

**Placeholder scan:** None found.

**Type consistency:**
- `"pending"` added to `TimelineCell.type` in types and rendered in Cell — consistent.
- `topic_id: f"pending:{cid}:{i}"` — string, matches `TimelineTopic.topic_id: string` — consistent.
- `call_updates` key shape matches `TimelineCell` interface — consistent.

**Edge cases handled:**
- Both `pending_topics` and `extraction_cache` are null → empty array, no rows appended.
- A call that has SOME topic_updates but not all → it's in `calls_with_updates`, so its raw cache is NOT used. This is correct: once a call has committed any topics, only the committed view is shown.
- Topics table is empty (all orphan-cleaned) → `topic_ids = []`, `updates = []`, `calls_with_updates = {}` → all calls fall into pending path. ✅
