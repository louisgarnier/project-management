# EPIC-8 Topics Timeline Grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat TopicsDashboard on the Board's Topics tab with a horizontally scrollable timeline grid showing one column per call and one row per topic, with per-cell type badges and expand-on-click detail.

**Architecture:** New backend endpoint builds the full topic × call matrix server-side. Frontend renders a sticky-left-column table that scrolls horizontally. Cells are classified as absent / not_discussed / new / followed_up / resolved and expand on click to show full detail.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Next.js (frontend), Supabase (DB — no migration needed).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/topics_service.py` | Modify | Add `list_topics_timeline(project_id, db)` |
| `backend/routers/topics.py` | Modify | Add `GET /projects/{id}/topics/timeline` |
| `backend/tests/test_topics.py` | Modify | Add `TestTopicsTimeline` class (3 tests) |
| `frontend/src/types/index.ts` | Modify | Add `TimelineCell`, `TimelineTopic`, `TopicsTimelineData` |
| `frontend/src/api/client.ts` | Modify | Add `topicsAPI.timeline(projectId)` |
| `frontend/src/components/TopicsTimeline.tsx` | Create | Timeline grid component |
| `frontend/app/projects/[id]/board/page.tsx` | Modify | Swap `TopicsDashboard` → `TopicsTimeline` on Topics tab |

---

## Task 1: Backend service — `list_topics_timeline`

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/tests/test_topics.py`

### Step 1.1 — Write the failing tests

Add this class at the bottom of `backend/tests/test_topics.py`:

```python
class TestTopicsTimeline(unittest.TestCase):

    @patch("backend.services.topics_service.get_client")
    def test_timeline_no_topics(self, mock_gc):
        """Empty project returns empty topics list and empty calls list."""
        from backend.services.topics_service import list_topics_timeline
        db = MagicMock()
        db.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        result = list_topics_timeline("proj-1", db)
        self.assertEqual(result["calls"], [])
        self.assertEqual(result["topics"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_new_and_not_discussed(self, mock_gc):
        """Topic raised in call 2 appears as new in call 2, not_discussed in call 3, absent in call 1."""
        from backend.services.topics_service import list_topics_timeline
        db = MagicMock()

        # calls for this project (done stage only)
        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
            {"id": "c3", "title": "Follow-up", "call_number": 3, "kanban_stage": "done"},
        ]
        # topics
        topics = [{"id": "t1", "name": "Risk Model", "first_raised_call_id": "c2"}]
        # topic_updates: one update in c2 (new), none in c3 (not_discussed)
        updates = [
            {
                "topic_id": "t1", "call_id": "c2",
                "summary": "First discussion", "follow_up_items": ["item1"],
                "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral",
            }
        ]
        # latest topic state
        latest = [{"id": "t1", "status": "open", "owner": "Us", "sentiment": "neutral"}]

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
            elif name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = topics
                m.select.return_value.in_.return_value.execute.return_value.data = latest
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.execute.return_value.data = updates
            return m
        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        self.assertEqual(len(result["calls"]), 3)
        self.assertEqual(len(result["topics"]), 1)

        t = result["topics"][0]
        self.assertNotIn("c1", t["call_updates"])                          # absent
        self.assertEqual(t["call_updates"]["c2"]["type"], "new")
        self.assertEqual(t["call_updates"]["c2"]["summary"], "First discussion")
        self.assertEqual(t["call_updates"]["c3"]["type"], "not_discussed")

    @patch("backend.services.topics_service.get_client")
    def test_timeline_followed_up_and_absent(self, mock_gc):
        """Topic raised in call 1 and followed up in call 2; call 3 absent because topic resolved."""
        from backend.services.topics_service import list_topics_timeline
        db = MagicMock()

        calls = [
            {"id": "c1", "title": "Kickoff", "call_number": 1, "kanban_stage": "done"},
            {"id": "c2", "title": "Review", "call_number": 2, "kanban_stage": "done"},
        ]
        topics = [{"id": "t1", "name": "Dashboard", "first_raised_call_id": "c1"}]
        updates = [
            {
                "topic_id": "t1", "call_id": "c1",
                "summary": "Raised", "follow_up_items": [], "decisions": [],
                "status": "open", "owner": "Us", "sentiment": "neutral",
            },
            {
                "topic_id": "t1", "call_id": "c2",
                "summary": "Resolved now", "follow_up_items": [], "decisions": [],
                "status": "resolved", "owner": "Us", "sentiment": "positive",
            },
        ]
        latest = [{"id": "t1", "status": "resolved", "owner": "Us", "sentiment": "positive"}]

        def table_side_effect(name):
            m = MagicMock()
            if name == "calls":
                m.select.return_value.eq.return_value.in_.return_value.order.return_value.execute.return_value.data = calls
            elif name == "topics":
                m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = topics
                m.select.return_value.in_.return_value.execute.return_value.data = latest
            elif name == "topic_updates":
                m.select.return_value.in_.return_value.execute.return_value.data = updates
            return m
        db.table.side_effect = table_side_effect

        result = list_topics_timeline("proj-1", db)
        t = result["topics"][0]
        self.assertEqual(t["call_updates"]["c1"]["type"], "new")
        self.assertEqual(t["call_updates"]["c2"]["type"], "followed_up")
        self.assertEqual(t["call_updates"]["c2"]["status"], "resolved")
```

- [ ] **Step 1.2 — Run tests to confirm they fail**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::TestTopicsTimeline -v
```
Expected: 3 failures — `ImportError` or `AttributeError` (function not yet defined).

- [ ] **Step 1.3 — Implement `list_topics_timeline` in `topics_service.py`**

Add this function after `list_project_topics` (around line 1093):

```python
def list_topics_timeline(project_id: str, db=None) -> dict:
    """
    Build the full topic × call matrix for the timeline grid.

    Returns:
      {
        "calls": [{"id", "title", "call_number", "kanban_stage"}, ...],  # ordered by call_number
        "topics": [{
          "topic_id", "name", "status", "owner", "sentiment",
          "first_raised_call_id",
          "call_updates": {
            "<call_id>": {
              "type": "new" | "followed_up" | "not_discussed",
              "summary": str,           # omitted for not_discussed
              "follow_up_items": [...], # omitted for not_discussed
              "decisions": [...],       # omitted for not_discussed
              "status": str,            # omitted for not_discussed
              "owner": str,             # omitted for not_discussed
              "sentiment": str,         # omitted for not_discussed
            }
          }
        }, ...]
      }

    Cell classification rules:
      - call_id < first_raised_call_id order → absent (key not present in call_updates)
      - call_id has a topic_update row        → "new" (first call) or "followed_up" (subsequent)
      - call_id >= first_raised and no row    → "not_discussed"
    """
    if db is None:
        db = get_client()

    # 1. Fetch all done/artifacts calls for this project, ordered by call_number
    COMPLETED_STAGES = ("call_topics", "project_matching", "project_updates", "artifacts", "done")
    all_calls = (
        db.table("calls")
        .select("id, title, call_number, kanban_stage")
        .eq("project_id", project_id)
        .in_("kanban_stage", list(COMPLETED_STAGES))
        .order("call_number")
        .execute()
        .data
    )
    if not all_calls:
        return {"calls": [], "topics": []}

    call_ids = [c["id"] for c in all_calls]
    call_order = {c["id"]: i for i, c in enumerate(all_calls)}

    # 2. Fetch all non-archived topics for this project
    topics = (
        db.table("topics")
        .select("id, name, first_raised_call_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    if not topics:
        return {"calls": all_calls, "topics": []}

    topic_ids = [t["id"] for t in topics]

    # 3. Fetch all topic_updates for these topics across all relevant calls
    updates = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, follow_up_items, decisions, status, owner, sentiment")
        .in_("topic_id", topic_ids)
        .execute()
        .data
    )
    # Index: topic_id → call_id → update row
    updates_index: dict[str, dict[str, dict]] = {}
    for u in updates:
        tid = u["topic_id"]
        cid = u["call_id"]
        if tid not in updates_index:
            updates_index[tid] = {}
        updates_index[tid][cid] = u

    # 4. Fetch latest state per topic (status/owner/sentiment for left column)
    latest_rows = (
        db.table("topics")
        .select("id, status, owner, sentiment")
        .in_("id", topic_ids)
        .execute()
        .data
    ) if topic_ids else []
    latest_state = {r["id"]: r for r in latest_rows}

    # 5. Build per-topic timeline
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
                # Topic didn't exist yet — absent (no key)
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
                # Topic existed but wasn't discussed in this call
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

    return {"calls": all_calls, "topics": result_topics}
```

- [ ] **Step 1.4 — Run tests to confirm they pass**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::TestTopicsTimeline -v
```
Expected: 3 tests pass.

- [ ] **Step 1.5 — Run full test suite to check for regressions**

```bash
python -m pytest backend/tests/ -v --tb=short
```
Expected: all existing tests still pass.

- [ ] **Step 1.6 — Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add list_topics_timeline service function"
```

---

## Task 2: Backend router — `GET /projects/{id}/topics/timeline`

**Files:**
- Modify: `backend/routers/topics.py`

- [ ] **Step 2.1 — Add import for `list_topics_timeline` at the top of `topics.py`**

Find the existing import line (around line 6-8):
```python
from backend.services.topics_service import (
    get_pending_topics, save_match_groups, run_merge_preview, validate_project_updates,
    run_extraction_background, run_merge_background,
    ...
)
```

Add `list_topics_timeline` to the import list.

- [ ] **Step 2.2 — Add the endpoint after the existing `list_topics` endpoint (after line ~254)**

```python
@router.get("/projects/{project_id}/topics/timeline")
async def get_topics_timeline(project_id: str):
    """Return the full topic × call matrix for the timeline grid."""
    logger.info(f"📥 [Topics] Timeline requested: project={project_id}")
    db = get_client()
    result = list_topics_timeline(project_id, db)
    logger.info(
        f"✅ [Topics] Timeline: {len(result['calls'])} calls, {len(result['topics'])} topics"
    )
    return result
```

- [ ] **Step 2.3 — Run the backend to verify the endpoint is reachable**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/ -v --tb=short
```
Expected: all tests pass.

- [ ] **Step 2.4 — Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: add GET /projects/{id}/topics/timeline endpoint"
```

---

## Task 3: Frontend types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 3.1 — Add the three new types at the bottom of `frontend/src/types/index.ts`**

```typescript
// ── EPIC-8: Topics Timeline ───────────────────────────────────────────────

export interface TimelineCell {
  type: "new" | "followed_up" | "not_discussed";
  summary?: string;
  follow_up_items?: string[];
  decisions?: string[];
  status?: string;
  owner?: string;
  sentiment?: string;
}

export interface TimelineTopic {
  topic_id: string;
  name: string;
  status: TopicStatus;
  owner: string;
  sentiment: TopicSentiment;
  first_raised_call_id: string | null;
  call_updates: Record<string, TimelineCell>;
}

export interface TopicsTimelineData {
  calls: Array<{ id: string; title: string; call_number: number; kanban_stage: string }>;
  topics: TimelineTopic[];
}
```

- [ ] **Step 3.2 — Type-check**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 3.3 — Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add TopicsTimelineData, TimelineTopic, TimelineCell types"
```

---

## Task 4: Frontend API client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 4.1 — Add import for `TopicsTimelineData` at the top of `client.ts`**

Find the existing type import line and add `TopicsTimelineData` to it:
```typescript
import type { ..., TopicsTimelineData } from "@/types";
```

- [ ] **Step 4.2 — Add `timeline` to `topicsAPI`**

Find `topicsAPI` in `client.ts` and add after `listForProject`:

```typescript
  timeline: (projectId: string) =>
    proxyFetch<TopicsTimelineData>(`/api/projects/${projectId}/topics/timeline`),
```

- [ ] **Step 4.3 — Type-check**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 4.4 — Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add topicsAPI.timeline client method"
```

---

## Task 5: `TopicsTimeline` component

**Files:**
- Create: `frontend/src/components/TopicsTimeline.tsx`

- [ ] **Step 5.1 — Create the component**

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import type { TopicsTimelineData, TimelineCell, TopicStatus, TopicSentiment } from "@/types";

type Props = { projectId: string };

// ── Style constants ───────────────────────────────────────────────────────

const STATUS_BADGE: Record<TopicStatus, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_BADGE: Record<TopicSentiment, React.CSSProperties> = {
  positive: { background: "#e3fcef", color: "#006644" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  concern:  { background: "#fff1f0", color: "#ae2a19" },
};

const BADGE_BASE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};

// ── Cell component ────────────────────────────────────────────────────────

function Cell({ cell }: { cell: TimelineCell | undefined }) {
  const [expanded, setExpanded] = useState(false);

  if (!cell) {
    // Absent — topic didn't exist yet
    return <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3", verticalAlign: "top" }} />;
  }

  if (cell.type === "not_discussed") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", textAlign: "center", color: "#bfc5ce",
        fontSize: 13, paddingTop: 14 }}>
        —
      </td>
    );
  }

  const isNew = cell.type === "new";
  const isResolved = cell.status === "resolved";

  const cellStyle: React.CSSProperties = isResolved
    ? { background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 5, padding: "7px 9px" }
    : isNew
      ? { background: "#fff7ec", border: "1px solid #ffe0b2", borderRadius: 5, padding: "7px 9px", cursor: "pointer" }
      : { background: "#f0f4ff", border: "1px solid #c0d0f0", borderRadius: 5, padding: "7px 9px", cursor: "pointer" };

  const badgeStyle: React.CSSProperties = isResolved
    ? { ...BADGE_BASE, background: "#006644", color: "white" }
    : isNew
      ? { ...BADGE_BASE, background: "#ff8b00", color: "white" }
      : { ...BADGE_BASE, background: "#0052cc", color: "white" };

  const badgeLabel = isResolved ? "✓ Resolved" : isNew ? "✦ New" : "Updated";

  const canExpand = !isResolved;

  return (
    <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
      verticalAlign: "top", padding: "10px 12px" }}>
      <div style={cellStyle} onClick={() => canExpand && setExpanded((v) => !v)}>
        <span style={badgeStyle}>{badgeLabel}</span>

        {cell.summary && (
          <div style={{
            fontSize: 11, color: "#172b4d", lineHeight: 1.45, marginTop: 5,
            display: "-webkit-box", WebkitLineClamp: expanded ? undefined : 2,
            WebkitBoxOrient: "vertical", overflow: expanded ? "visible" : "hidden",
          }}>
            {cell.summary}
          </div>
        )}

        {!expanded && (cell.follow_up_items ?? []).length > 0 && (
          <div style={{ fontSize: 10, color: "#5e6c84", marginTop: 4 }}>
            {cell.follow_up_items!.length} follow-up{cell.follow_up_items!.length !== 1 ? "s" : ""}
          </div>
        )}

        {canExpand && expanded && (
          <div style={{ marginTop: 6, borderTop: "1px solid #dfe1e6", paddingTop: 6 }}>
            {(cell.follow_up_items ?? []).length > 0 && (
              <>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  color: "#97a0af", marginBottom: 3 }}>Follow-ups</div>
                {cell.follow_up_items!.map((item, i) => (
                  <div key={i} style={{ fontSize: 10, color: "#5e6c84", padding: "1px 0" }}>
                    → {item}
                  </div>
                ))}
              </>
            )}
            {(cell.decisions ?? []).length > 0 && (
              <>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  color: "#97a0af", marginTop: 6, marginBottom: 3 }}>Decisions</div>
                {cell.decisions!.map((d, i) => (
                  <div key={i} style={{ fontSize: 10, color: "#172b4d", padding: "1px 0" }}>
                    ✓ {d}
                  </div>
                ))}
              </>
            )}
          </div>
        )}

        {canExpand && (
          <div style={{ fontSize: 9, color: "#97a0af", marginTop: 4 }}>
            {expanded ? "▴ collapse" : "▾ expand"}
          </div>
        )}
      </div>
    </td>
  );
}

// ── Main component ────────────────────────────────────────────────────────

export default function TopicsTimeline({ projectId }: Props) {
  const [data, setData] = useState<TopicsTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await topicsAPI.timeline(projectId);
      setData(result);
    } catch {
      setError("Failed to load topics timeline.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
    </div>
  );

  if (error) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
    </div>
  );

  if (!data || data.calls.length === 0 || data.topics.length === 0) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>
        {!data || data.calls.length === 0
          ? "No completed calls yet."
          : "No topics defined yet."}
      </p>
    </div>
  );

  return (
    <div style={{ flex: 1, overflow: "auto", background: "#f4f5f7" }}>
      <table style={{ borderCollapse: "collapse", minWidth: "100%", background: "white" }}>
        <thead>
          <tr>
            {/* Sticky left header */}
            <th style={{
              position: "sticky", left: 0, zIndex: 2, background: "#f4f5f7",
              width: 220, minWidth: 220, maxWidth: 220,
              borderRight: "2px solid #dfe1e6", borderBottom: "2px solid #dfe1e6",
              padding: "10px 12px", textAlign: "left",
              fontSize: 10, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: ".05em", color: "#5e6c84",
            }}>
              Topic
            </th>
            {/* One column per call */}
            {data.calls.map((c) => (
              <th key={c.id} style={{
                width: 180, minWidth: 180, maxWidth: 180,
                background: "#f4f5f7", padding: "10px 12px",
                borderRight: "1px solid #f0f1f3", borderBottom: "2px solid #dfe1e6",
                textAlign: "left", whiteSpace: "nowrap",
              }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#172b4d", display: "block" }}>
                  Call {c.call_number}
                </span>
                <span style={{
                  fontSize: 10, color: "#97a0af", display: "block",
                  overflow: "hidden", textOverflow: "ellipsis", maxWidth: 156,
                }}>
                  {c.title}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.topics.map((topic) => {
            const isResolved = topic.status === "resolved";
            return (
              <tr key={topic.topic_id} style={{ borderBottom: "1px solid #f0f1f3", opacity: isResolved ? 0.65 : 1 }}>
                {/* Sticky left column */}
                <td style={{
                  position: "sticky", left: 0, background: "white", zIndex: 1,
                  width: 220, minWidth: 220, maxWidth: 220,
                  borderRight: "2px solid #dfe1e6", padding: "10px 12px", verticalAlign: "top",
                }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", marginBottom: 4 }}>
                    {topic.name}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    <span style={{ ...BADGE_BASE, ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open) }}>
                      {topic.status.replace("_", " ")}
                    </span>
                    <span style={{ ...BADGE_BASE, ...(SENTIMENT_BADGE[topic.sentiment] ?? SENTIMENT_BADGE.neutral) }}>
                      {topic.sentiment}
                    </span>
                    <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>
                      {topic.owner}
                    </span>
                  </div>
                </td>
                {/* One cell per call */}
                {data.calls.map((c) => (
                  <Cell key={c.id} cell={topic.call_updates[c.id]} />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5.2 — Type-check**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 5.3 — Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add TopicsTimeline component"
```

---

## Task 6: Wire into board page

**Files:**
- Modify: `frontend/app/projects/[id]/board/page.tsx`

- [ ] **Step 6.1 — Replace `TopicsDashboard` import with `TopicsTimeline`**

In `frontend/app/projects/[id]/board/page.tsx`:

Replace:
```typescript
import TopicsDashboard from "@/components/TopicsDashboard";
```
With:
```typescript
import TopicsTimeline from "@/components/TopicsTimeline";
```

- [ ] **Step 6.2 — Replace the render call**

Replace:
```typescript
      {activeTab === "topics" ? (
        <TopicsDashboard projectId={projectId} />
```
With:
```typescript
      {activeTab === "topics" ? (
        <TopicsTimeline projectId={projectId} />
```

- [ ] **Step 6.3 — Type-check**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 6.4 — Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: wire TopicsTimeline into board Topics tab"
```

---

## Task 7: Manual verification

- [ ] **Step 7.1** — Open the app, navigate to a project → Board → Topics tab. Confirm the timeline grid renders with one column per call.
- [ ] **Step 7.2** — Confirm the left column is sticky when scrolling horizontally.
- [ ] **Step 7.3** — Confirm cell types: blank for absent, "—" for not discussed, orange ✦ New, blue Updated, green ✓ Resolved.
- [ ] **Step 7.4** — Click a New or Updated cell → confirm it expands showing follow-ups and decisions. Click again → collapses.
- [ ] **Step 7.5** — Confirm resolved topic rows render at 65% opacity.
- [ ] **Step 7.6** — Final commit if any minor fixes applied during verification.
