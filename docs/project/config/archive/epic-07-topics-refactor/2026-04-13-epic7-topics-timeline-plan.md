# EPIC-7: Topics Timeline Grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat Topics dashboard on the Board page with a timeline grid where rows = topics and columns = one per call, showing how each topic evolved across calls.

**Architecture:** New backend endpoint `/projects/{id}/topics/timeline` returns pre-computed cell types (new / followed_up / not_discussed / absent) so the frontend is a pure render. The existing `TopicsDashboard` component is replaced by `TopicsTimeline`; call-level `TopicsPanel` is unchanged. The `topic_updates` table already holds all the data needed — no schema migration required.

**Tech Stack:** FastAPI, Supabase (postgres via supabase-py), Next.js 15 App Router, React 19, TypeScript, inline styles throughout (no Tailwind in this component per existing codebase pattern in `TopicsDashboard.tsx`).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/topics_service.py` | Modify | Add `list_topics_timeline(project_id, db)` |
| `backend/routers/topics.py` | Modify | Add `GET /projects/{id}/topics/timeline` endpoint |
| `backend/tests/test_topics.py` | Modify | Add 3 tests for the new endpoint |
| `frontend/src/types/index.ts` | Modify | Add `TimelineCallSummary`, `TimelineCell`, `TimelineTopic`, `TopicsTimelineData` |
| `frontend/src/api/client.ts` | Modify | Add `topicsAPI.timeline(projectId)` |
| `frontend/src/components/TopicsTimeline.tsx` | Create | Timeline grid component |
| `frontend/app/projects/[id]/board/page.tsx` | Modify | Swap `TopicsDashboard` → `TopicsTimeline` |

---

## Task 1: Backend service — `list_topics_timeline`

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/tests/test_topics.py`

- [ ] **Step 1: Write the failing tests**

Open `backend/tests/test_topics.py`. Add the following three tests after the existing test suite (do not remove existing tests):

```python
# ─── Timeline tests ──────────────────────────────────────────────────────────

def _make_call(call_id: str, title: str, stage: str = "done", project_id: str = "proj-1") -> dict:
    return {"id": call_id, "title": title, "kanban_stage": stage,
            "project_id": project_id, "created_at": f"2026-01-0{call_id[-1]}T00:00:00"}


def _make_topic(topic_id: str, name: str, first_call_id: str | None = None) -> dict:
    return {"id": topic_id, "name": name, "first_raised_call_id": first_call_id,
            "archived": False, "project_id": "proj-1", "created_at": "2026-01-01T00:00:00"}


def _make_update(topic_id: str, call_id: str, status: str = "open",
                 summary: str = "summary", owner: str = "Us",
                 sentiment: str = "neutral") -> dict:
    return {"topic_id": topic_id, "call_id": call_id, "summary": summary,
            "follow_up_items": [], "decisions": [], "status": status,
            "owner": owner, "sentiment": sentiment}


class TestTopicsTimeline(unittest.TestCase):
    """Tests for list_topics_timeline."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("backend.services.topics_service.get_client")
    def test_timeline_no_topics(self, mock_get_client):
        """Returns empty topics list when project has no topics."""
        db = MagicMock()
        mock_get_client.return_value = db
        call1 = _make_call("call-1", "Call 1")
        db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [call1]
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []

        result = self._run(list_topics_timeline("proj-1", db))

        self.assertEqual(result["calls"][0]["number"], 1)
        self.assertEqual(result["topics"], [])

    @patch("backend.services.topics_service.get_client")
    def test_timeline_new_and_not_discussed(self, mock_get_client):
        """Topic is 'new' in call-1 and 'not_discussed' in call-2 when no update exists."""
        db = MagicMock()
        mock_get_client.return_value = db

        topic_a = _make_topic("topic-a", "Budget", first_call_id="call-1")
        call1 = _make_call("call-1", "Call 1")
        call2 = _make_call("call-2", "Call 2")
        update_a_c1 = _make_update("topic-a", "call-1", status="open")

        # Calls query
        calls_q = db.table.return_value.select.return_value.eq.return_value.order.return_value.execute
        calls_q.return_value.data = [call1, call2]
        # Topics query
        topics_q = db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute
        topics_q.return_value.data = [topic_a]
        # Latest update per topic
        latest_q = (db.table.return_value.select.return_value.eq.return_value
                    .order.return_value.limit.return_value.execute)
        latest_q.return_value.data = [update_a_c1]
        # All updates query (in_ filter)
        all_q = db.table.return_value.select.return_value.in_.return_value.execute
        all_q.return_value.data = [update_a_c1]

        result = self._run(list_topics_timeline("proj-1", db))

        topic = result["topics"][0]
        self.assertEqual(topic["call_updates"]["call-1"]["type"], "new")
        self.assertEqual(topic["call_updates"]["call-2"]["type"], "not_discussed")

    @patch("backend.services.topics_service.get_client")
    def test_timeline_followed_up_and_absent(self, mock_get_client):
        """Topic first raised in call-2: absent from call-1, followed_up in call-3."""
        db = MagicMock()
        mock_get_client.return_value = db

        topic_b = _make_topic("topic-b", "Timeline", first_call_id="call-2")
        call1 = _make_call("call-1", "Call 1")
        call2 = _make_call("call-2", "Call 2")
        call3 = _make_call("call-3", "Call 3")
        update_b_c2 = _make_update("topic-b", "call-2", status="open")
        update_b_c3 = _make_update("topic-b", "call-3", status="in_progress")

        calls_q = db.table.return_value.select.return_value.eq.return_value.order.return_value.execute
        calls_q.return_value.data = [call1, call2, call3]
        topics_q = db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute
        topics_q.return_value.data = [topic_b]
        latest_q = (db.table.return_value.select.return_value.eq.return_value
                    .order.return_value.limit.return_value.execute)
        latest_q.return_value.data = [update_b_c3]
        all_q = db.table.return_value.select.return_value.in_.return_value.execute
        all_q.return_value.data = [update_b_c2, update_b_c3]

        result = self._run(list_topics_timeline("proj-1", db))

        topic = result["topics"][0]
        self.assertNotIn("call-1", topic["call_updates"])   # absent — topic post-dates this call
        self.assertEqual(topic["call_updates"]["call-2"]["type"], "new")
        self.assertEqual(topic["call_updates"]["call-3"]["type"], "followed_up")
        self.assertEqual(topic["call_updates"]["call-3"]["status"], "in_progress")
```

Also add `list_topics_timeline` to the import at the top of `test_topics.py`:

```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, TopicUpdate,
)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::TestTopicsTimeline -v
```

Expected: `ImportError: cannot import name 'list_topics_timeline'`

- [ ] **Step 3: Implement `list_topics_timeline` in `topics_service.py`**

Add the following function at the end of `backend/services/topics_service.py`, after `list_project_topics`:

```python
async def list_topics_timeline(project_id: str, db=None) -> dict:
    """
    Build a full timeline of topics × calls for the project.

    Returns:
      {
        "calls": [{"id": str, "title": str, "number": int, "kanban_stage": str}, ...],
        "topics": [
          {
            "topic_id": str,
            "name": str,
            "status": str,          # current (latest) status
            "owner": str,           # current (latest) owner
            "sentiment": str,       # current (latest) sentiment
            "first_raised_call_id": str | None,
            "call_updates": {
              "<call_id>": {
                "type": "new" | "followed_up" | "not_discussed",
                "summary": str,           # absent when type == "not_discussed"
                "follow_up_items": [...], # absent when type == "not_discussed"
                "decisions": [...],       # absent when type == "not_discussed"
                "status": str,            # absent when type == "not_discussed"
                "owner": str,             # absent when type == "not_discussed"
                "sentiment": str,         # absent when type == "not_discussed"
              },
              # call_id is ABSENT (not in dict) when topic did not yet exist at that call
            }
          },
          ...
        ]
      }
    """
    if db is None:
        db = get_client()

    # 1. All calls for the project, ordered oldest-first
    calls_rows = (
        db.table("calls")
        .select("id, title, kanban_stage, created_at")
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
        .data
    )
    calls = [
        {"id": r["id"], "title": r["title"], "number": i + 1, "kanban_stage": r["kanban_stage"]}
        for i, r in enumerate(calls_rows)
    ]
    call_index = {r["id"]: i for i, r in enumerate(calls_rows)}

    # 2. All non-archived topics
    topics_rows = (
        db.table("topics")
        .select("id, name, first_raised_call_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    if not topics_rows:
        return {"calls": calls, "topics": []}

    topic_ids = [t["id"] for t in topics_rows]

    # 3. Latest update per topic → current status / owner / sentiment
    latest_by_topic: dict[str, dict] = {}
    for topic_id in topic_ids:
        updates = (
            db.table("topic_updates")
            .select("summary, follow_up_items, decisions, status, owner, sentiment")
            .eq("topic_id", topic_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        latest_by_topic[topic_id] = updates[0] if updates else {}

    # 4. All topic_updates for the project in one query
    all_updates_rows = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, follow_up_items, decisions, status, owner, sentiment")
        .in_("topic_id", topic_ids)
        .execute()
        .data
    )
    # updates_by_topic[topic_id][call_id] = update row
    updates_by_topic: dict[str, dict[str, dict]] = {}
    for u in all_updates_rows:
        updates_by_topic.setdefault(u["topic_id"], {})[u["call_id"]] = u

    # 5. Build per-topic timeline
    timeline_topics = []
    for t in topics_rows:
        topic_id = t["id"]
        first_call_id = t.get("first_raised_call_id")
        # Index of the call where this topic first appeared (-1 = unknown/manual)
        first_call_idx = call_index.get(first_call_id, -1) if first_call_id else -1

        latest = latest_by_topic.get(topic_id, {})
        updates_for_topic = updates_by_topic.get(topic_id, {})

        call_updates: dict[str, dict] = {}
        for i, call_row in enumerate(calls_rows):
            call_id = call_row["id"]

            # Skip calls that predate this topic (absent from the dict = empty cell in UI)
            if first_call_idx >= 0 and i < first_call_idx:
                continue

            if call_id in updates_for_topic:
                u = updates_for_topic[call_id]
                cell_type = "new" if call_id == first_call_id else "followed_up"
                call_updates[call_id] = {
                    "type": cell_type,
                    "summary": u.get("summary") or "",
                    "follow_up_items": u.get("follow_up_items") or [],
                    "decisions": u.get("decisions") or [],
                    "status": u.get("status", "open"),
                    "owner": u.get("owner", "Us"),
                    "sentiment": u.get("sentiment", "neutral"),
                }
            else:
                call_updates[call_id] = {"type": "not_discussed"}

        timeline_topics.append({
            "topic_id": topic_id,
            "name": t["name"],
            "status": latest.get("status", "open"),
            "owner": latest.get("owner", "Us"),
            "sentiment": latest.get("sentiment", "neutral"),
            "first_raised_call_id": first_call_id,
            "call_updates": call_updates,
        })

    return {"calls": calls, "topics": timeline_topics}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python -m pytest backend/tests/test_topics.py::TestTopicsTimeline -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full backend test suite**

```bash
python -m pytest backend/tests/ -v
```

Expected: all existing tests still pass (no regressions)

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: add list_topics_timeline service function" "backend/services/topics_service.py" "backend/tests/test_topics.py"
```

---

## Task 2: Backend router — timeline endpoint

**Files:**
- Modify: `backend/routers/topics.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_topics.py` in a new class `TestTopicsTimelineEndpoint`:

```python
class TestTopicsTimelineEndpoint(unittest.TestCase):

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("backend.routers.topics.list_topics_timeline")
    def test_timeline_endpoint_returns_data(self, mock_timeline):
        """GET /projects/{id}/topics/timeline calls service and returns result."""
        mock_timeline.return_value = asyncio.coroutine(
            lambda: {"calls": [], "topics": []}
        )()
        # Use AsyncMock for async function
        async def fake_timeline(*args, **kwargs):
            return {"calls": [{"id": "c1", "title": "Call 1", "number": 1, "kanban_stage": "done"}],
                    "topics": []}
        mock_timeline.side_effect = fake_timeline

        response = client.get("/api/projects/proj-1/topics/timeline")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("calls", data)
        self.assertIn("topics", data)
```

Also add the import at the top of the test file imports section:

```python
from backend.routers.topics import router  # already imported via `client`
```

(The `client` is already set up in `test_topics.py` — check top of file and use the same `TestClient` pattern as existing tests.)

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest backend/tests/test_topics.py::TestTopicsTimelineEndpoint -v
```

Expected: FAIL (endpoint does not exist yet → 404 or ImportError)

- [ ] **Step 3: Add the endpoint to `backend/routers/topics.py`**

Add the import at the top:

```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, TopicUpdate,
)
```

Add the endpoint after `list_topics`:

```python
@router.get("/projects/{project_id}/topics/timeline")
async def timeline(project_id: str):
    logger.info(f"📥 [Topics] Timeline requested: project={project_id}")
    db = get_client()
    result = await list_topics_timeline(project_id, db)
    logger.info(
        f"✅ [Topics] Timeline returned {len(result['topics'])} topics, "
        f"{len(result['calls'])} calls"
    )
    return result
```

- [ ] **Step 4: Run the endpoint test to verify it passes**

```bash
python -m pytest backend/tests/test_topics.py::TestTopicsTimelineEndpoint -v
```

Expected: PASS

- [ ] **Step 5: Run full backend test suite**

```bash
python -m pytest backend/tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: add GET /projects/{id}/topics/timeline endpoint" "backend/routers/topics.py" "backend/tests/test_topics.py"
```

---

## Task 3: Frontend — types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add types to `frontend/src/types/index.ts`**

Append the following after the `CallBrief` interface (after line 99):

```typescript
// ── Topics Timeline ──────────────────────────────────────────────────────────

export interface TimelineCallSummary {
  id: string;
  title: string;
  number: number;
  kanban_stage: KanbanStage;
}

export type TimelineCellType = "new" | "followed_up" | "not_discussed";

export interface TimelineCell {
  type: TimelineCellType;
  summary?: string;
  follow_up_items?: string[];
  decisions?: string[];
  status?: TopicStatus;
  owner?: TopicOwner;
  sentiment?: TopicSentiment;
}

export interface TimelineTopic {
  topic_id: string;
  name: string;
  status: TopicStatus;
  owner: TopicOwner;
  sentiment: TopicSentiment;
  first_raised_call_id: string | null;
  call_updates: Record<string, TimelineCell>;  // key = call_id, absent = topic not yet raised
}

export interface TopicsTimelineData {
  calls: TimelineCallSummary[];
  topics: TimelineTopic[];
}
```

- [ ] **Step 2: Add `topicsAPI.timeline` to `frontend/src/api/client.ts`**

Find the `topicsAPI` export. It currently ends with `listForProject`. Add `timeline` to it:

```typescript
export const topicsAPI = {
  // ... existing methods unchanged ...
  listForProject: (projectId: string) =>
    proxyFetch<TopicData[]>(`/api/projects/${projectId}/topics`),
  timeline: (projectId: string) =>
    proxyFetch<TopicsTimelineData>(`/api/projects/${projectId}/topics/timeline`),
};
```

Also add `TopicsTimelineData` to the type import at the top of `client.ts`:

```typescript
import type {
  Project, Call, CallFile, ArtifactType, Artifact, LLMProvider, ArtifactMode,
  TopicData, TopicSavePayload, CallBrief, TopicsTimelineData,
} from "@/types";
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-7] feat: add TopicsTimelineData types and API client method" "frontend/src/types/index.ts" "frontend/src/api/client.ts"
```

---

## Task 4: Frontend — `TopicsTimeline` component

**Files:**
- Create: `frontend/src/components/TopicsTimeline.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/TopicsTimeline.tsx` with this exact content:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  TopicsTimelineData, TimelineTopic, TimelineCell,
  TopicStatus, TopicSentiment,
} from "@/types";

type Props = { projectId: string };

// ── Style constants ───────────────────────────────────────────────────────────

const BADGE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", display: "inline-block",
};

const STATUS_STYLE: Record<TopicStatus, React.CSSProperties> = {
  open:        { background: "#fff4e6", color: "#974f0c" },
  in_progress: { background: "#e9f0ff", color: "#0052cc" },
  resolved:    { background: "#bbf7d0", color: "#15803d" },
};

const SENT_STYLE: Record<TopicSentiment, React.CSSProperties> = {
  concern:  { background: "#fff1f0", color: "#ae2a19" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  positive: { background: "#e3fcef", color: "#006644" },
};

const STATUS_LABEL: Record<TopicStatus, string> = {
  open: "Open", in_progress: "In Progress", resolved: "Resolved",
};

// ── Cell renderer ─────────────────────────────────────────────────────────────

function TimelineCell({ cell }: { cell: TimelineCell | undefined }) {
  if (!cell) {
    // Topic did not yet exist at this call
    return <div style={{ flex: 1 }} />;
  }

  if (cell.type === "not_discussed") {
    return (
      <div style={{
        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        color: "#b3bac5", fontSize: 13,
      }}>
        —
      </div>
    );
  }

  const isNew      = cell.type === "new";
  const isResolved = cell.status === "resolved";

  return (
    <div style={{ flex: 1, padding: "6px 8px", display: "flex", flexDirection: "column", gap: 4 }}>
      {/* Type badge */}
      {isNew ? (
        <span style={{ ...BADGE, background: "#fff4e6", color: "#974f0c" }}>New ✦</span>
      ) : isResolved ? (
        <span style={{ ...BADGE, background: "#bbf7d0", color: "#15803d" }}>✓ Resolved</span>
      ) : (
        <span style={{ ...BADGE, background: "#e9f0ff", color: "#0052cc" }}>Updated</span>
      )}

      {/* Summary (2 lines max) */}
      {cell.summary && (
        <div style={{
          fontSize: 10, color: "#172b4d", lineHeight: 1.4,
          display: "-webkit-box", WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical", overflow: "hidden",
        }}>
          {cell.summary}
        </div>
      )}

      {/* Follow-up count */}
      {(cell.follow_up_items?.length ?? 0) > 0 && (
        <div style={{ fontSize: 9, color: "#5e6c84" }}>
          → {cell.follow_up_items!.length} follow-up{cell.follow_up_items!.length > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}

// ── Topic row ─────────────────────────────────────────────────────────────────

function TopicRow({ topic, callIds }: { topic: TimelineTopic; callIds: string[] }) {
  const isResolved = topic.status === "resolved";

  return (
    <div style={{
      display: "flex", borderBottom: "1px solid #f4f5f7",
      opacity: isResolved ? 0.65 : 1,
      minHeight: 64,
    }}>
      {/* Topic name + current state (fixed left column) */}
      <div style={{
        width: 220, flexShrink: 0, padding: "8px 12px",
        borderRight: "1px solid #dfe1e6", display: "flex", flexDirection: "column", gap: 4,
        position: "sticky", left: 0, background: "white", zIndex: 1,
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", lineHeight: 1.3 }}>
          {topic.name}
        </span>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          <span style={{ ...BADGE, ...STATUS_STYLE[topic.status] }}>
            {STATUS_LABEL[topic.status]}
          </span>
          <span style={{ ...BADGE, background: "#f4f5f7", color: "#5e6c84" }}>
            {topic.owner}
          </span>
          <span style={{ ...BADGE, ...SENT_STYLE[topic.sentiment] }}>
            {topic.sentiment}
          </span>
        </div>
      </div>

      {/* One cell per call */}
      {callIds.map((callId) => (
        <div key={callId} style={{
          width: 160, flexShrink: 0, borderRight: "1px solid #f4f5f7",
          display: "flex",
        }}>
          <TimelineCell cell={topic.call_updates[callId]} />
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function TopicsTimeline({ projectId }: Props) {
  const [data, setData]       = useState<TopicsTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Loading topics timeline", { component: "TopicsTimeline", data: { projectId } });
      const result = await topicsAPI.timeline(projectId);
      setData(result);
    } catch (err) {
      logger.error("Failed to load timeline", { component: "TopicsTimeline", data: err });
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

  if (!data || data.topics.length === 0) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>
        {!data || data.calls.length === 0
          ? "No calls yet."
          : "No topics yet. Complete a call's topics stage to see the timeline."}
      </p>
    </div>
  );

  const callIds = data.calls.map((c) => c.id);

  return (
    <div style={{ flex: 1, overflowX: "auto", overflowY: "auto", padding: 16 }}>
      <div style={{
        display: "inline-block", minWidth: "100%",
        background: "white", border: "1px solid #dfe1e6",
        borderRadius: 8, overflow: "hidden",
      }}>
        {/* Header row */}
        <div style={{ display: "flex", background: "#f4f5f7", borderBottom: "1px solid #dfe1e6" }}>
          {/* Topic column header */}
          <div style={{
            width: 220, flexShrink: 0,
            padding: "8px 12px", borderRight: "1px solid #dfe1e6",
            position: "sticky", left: 0, background: "#f4f5f7", zIndex: 2,
          }}>
            <span style={{
              fontSize: 9, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: "0.06em", color: "#97a0af",
            }}>
              Topic
            </span>
          </div>
          {/* Call column headers */}
          {data.calls.map((call) => (
            <div key={call.id} style={{
              width: 160, flexShrink: 0, padding: "8px 12px",
              borderRight: "1px solid #dfe1e6",
            }}>
              <div style={{
                fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                letterSpacing: "0.06em", color: "#97a0af", marginBottom: 2,
              }}>
                Call {call.number}
              </div>
              <div style={{
                fontSize: 10, color: "#5e6c84", overflow: "hidden",
                textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}>
                {call.title}
              </div>
            </div>
          ))}
        </div>

        {/* Topic rows */}
        {data.topics.map((topic) => (
          <TopicRow key={topic.topic_id} topic={topic} callIds={callIds} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Run ESLint**

```bash
npx eslint src/components/TopicsTimeline.tsx
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-7] feat: add TopicsTimeline grid component" "frontend/src/components/TopicsTimeline.tsx"
```

---

## Task 5: Wire into board page

**Files:**
- Modify: `frontend/app/projects/[id]/board/page.tsx`

- [ ] **Step 1: Update the board page**

In `frontend/app/projects/[id]/board/page.tsx`:

1. Replace the import of `TopicsDashboard` with `TopicsTimeline`:

```typescript
// Remove:
import TopicsDashboard from "@/components/TopicsDashboard";

// Add:
import TopicsTimeline from "@/components/TopicsTimeline";
```

2. Replace `<TopicsDashboard projectId={projectId} />` with `<TopicsTimeline projectId={projectId} />`:

```tsx
// Remove:
{activeTab === "topics" ? (
  <TopicsDashboard projectId={projectId} />
) : ...

// Replace with:
{activeTab === "topics" ? (
  <TopicsTimeline projectId={projectId} />
) : ...
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Run ESLint**

```bash
npx eslint app/projects/\[id\]/board/page.tsx
```

Expected: 0 errors

- [ ] **Step 4: Run full frontend lint check**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx eslint .
```

Expected: 0 errors, 0 warnings

- [ ] **Step 5: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-7] feat: wire TopicsTimeline into board page, replace flat dashboard" "frontend/app/projects/[id]/board/page.tsx"
```

---

## Post-build checklist

- [ ] All 3 new backend tests pass (`TestTopicsTimeline`, `TestTopicsTimelineEndpoint`)
- [ ] Full backend suite passes (`python -m pytest backend/tests/ -v`)
- [ ] `npx tsc --noEmit` → 0 errors
- [ ] `npx eslint .` → 0 errors
- [ ] Manual test: Board → Topics tab shows timeline grid with columns per call
- [ ] Manual test: Topics first raised in call 2 show empty cell under call 1
- [ ] Manual test: Topics not discussed in a call show "—" grey cell
- [ ] Manual test: New topics show orange "New ✦" badge with truncated summary
- [ ] Manual test: Updated topics show "Updated" badge with summary
- [ ] Manual test: Resolved topics show green "✓ Resolved" badge at 65% opacity row
- [ ] Update `docs/project/config/build-log.md` — add EPIC-7 entry
- [ ] Update `docs/project/config/epics/ACTIVE.md` — mark EPIC-7 complete
