# EPIC-8: Topics Timeline Grid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /projects/{id}/topics/timeline` endpoint and a `TopicsTimeline` React component that renders a horizontally scrollable topic × call matrix, replacing the flat `TopicsDashboard` on the Board Topics tab.

**Architecture:** Backend builds the full matrix (topics as rows, calls as columns) with each cell pre-classified as `new`, `followed_up`, `not_discussed`, or absent. Frontend renders the grid with a sticky left column of topic names/badges and one 160 px column per call. Cell appearance and row opacity are derived entirely from the pre-classified data — no computation in the component.

**Tech Stack:** FastAPI, supabase-py, Next.js 15 App Router, React 19, TypeScript, inline styles.

**Context files to read before starting:**
- `backend/services/topics_service.py` — `_get_previous_topics`, `list_project_topics`, DB query patterns
- `backend/routers/topics.py` — existing endpoint patterns, router prefix (`/api`)
- `backend/tests/test_calls.py` — mock pattern used throughout the test suite
- `frontend/src/types/index.ts` — existing type definitions to extend
- `frontend/src/api/client.ts` — `topicsAPI` export to extend
- `frontend/src/components/TopicsDashboard.tsx` — component being replaced (style tokens to reuse)
- `frontend/app/projects/[id]/board/page.tsx` — where `TopicsDashboard` is imported and rendered

---

## File Map

| File | Action | What changes |
|---|---|---|
| `backend/services/topics_service.py` | Modify | Add `list_topics_timeline(project_id, db)` |
| `backend/routers/topics.py` | Modify | Add `GET /projects/{id}/topics/timeline` |
| `backend/tests/test_topics_timeline.py` | Create | 3 endpoint tests |
| `frontend/src/types/index.ts` | Modify | Add `TopicsTimelineData`, `TimelineTopic`, `TimelineCell` |
| `frontend/src/api/client.ts` | Modify | Add `topicsAPI.timeline(projectId)` |
| `frontend/src/components/TopicsTimeline.tsx` | Create | Timeline grid component |
| `frontend/app/projects/[id]/board/page.tsx` | Modify | Import `TopicsTimeline`, replace `TopicsDashboard` |

---

## Task 1: Backend — `list_topics_timeline` service + endpoint

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/routers/topics.py`

- [ ] **Step 1: Add `list_topics_timeline` to `backend/services/topics_service.py`**

Append this function after `list_project_topics` (end of file):

```python
def list_topics_timeline(project_id: str, db=None) -> dict:
    """
    Returns the full topic × call matrix for a project.

    Response shape:
      {
        "calls": [{"id", "title", "number", "kanban_stage"}, ...],   # ordered by created_at
        "topics": [{
          "topic_id", "name", "status", "owner", "sentiment",
          "first_raised_call_id",
          "call_updates": {
            "<call_id>": {"type": "new|followed_up|not_discussed", "summary?", ...}
          }
        }, ...]
      }

    Cell classification:
      - call_id absent from call_updates   → topic did not exist yet (absent state in UI)
      - type = "new"                        → this call is first_raised_call_id for the topic
      - type = "followed_up"               → subsequent call that updated the topic
      - type = "not_discussed"             → call after topic existed, but no update recorded
    """
    if db is None:
        db = get_client()

    # 1. All calls for the project, oldest first
    calls_rows = (
        db.table("calls")
        .select("id, title, kanban_stage, created_at")
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
        .data
    )
    calls_out = [
        {
            "id": c["id"],
            "title": c["title"],
            "number": i + 1,
            "kanban_stage": c["kanban_stage"],
        }
        for i, c in enumerate(calls_rows)
    ]
    call_ids_ordered = [c["id"] for c in calls_rows]
    call_position = {c["id"]: i for i, c in enumerate(calls_rows)}

    # 2. Non-archived topics
    topics_rows = (
        db.table("topics")
        .select("id, name, first_raised_call_id")
        .eq("project_id", project_id)
        .eq("archived", False)
        .execute()
        .data
    )
    if not topics_rows:
        return {"calls": calls_out, "topics": []}

    topic_ids = [t["id"] for t in topics_rows]

    # 3. All topic_updates for these topics
    updates_rows = (
        db.table("topic_updates")
        .select("topic_id, call_id, summary, follow_up_items, decisions, status, owner, sentiment")
        .in_("topic_id", topic_ids)
        .execute()
        .data
    )

    # Index: topic_id → {call_id → update_row}
    updates_by_topic: dict[str, dict] = {}
    for u in updates_rows:
        updates_by_topic.setdefault(u["topic_id"], {})[u["call_id"]] = u

    topics_out = []
    for t in topics_rows:
        first_raised = t["first_raised_call_id"]
        first_pos = call_position.get(first_raised, -1)
        topic_updates = updates_by_topic.get(t["id"], {})

        # Current status/owner/sentiment = latest call's update fields
        if topic_updates:
            latest_cid = max(topic_updates, key=lambda cid: call_position.get(cid, -1))
            latest = topic_updates[latest_cid]
            current_status = latest.get("status", "open")
            current_owner = latest.get("owner", "Us")
            current_sentiment = latest.get("sentiment", "neutral")
        else:
            current_status, current_owner, current_sentiment = "open", "Us", "neutral"

        call_updates: dict[str, dict] = {}
        for call_id in call_ids_ordered:
            pos = call_position[call_id]
            if pos < first_pos:
                # Absent: topic didn't exist at this call — omit from call_updates
                continue
            update = topic_updates.get(call_id)
            if update:
                utype = "new" if call_id == first_raised else "followed_up"
                call_updates[call_id] = {
                    "type": utype,
                    "summary": update.get("summary"),
                    "follow_up_items": update.get("follow_up_items", []),
                    "decisions": update.get("decisions", []),
                    "status": update.get("status"),
                    "owner": update.get("owner"),
                    "sentiment": update.get("sentiment"),
                }
            else:
                call_updates[call_id] = {"type": "not_discussed"}

        topics_out.append({
            "topic_id": t["id"],
            "name": t["name"],
            "status": current_status,
            "owner": current_owner,
            "sentiment": current_sentiment,
            "first_raised_call_id": first_raised,
            "call_updates": call_updates,
        })

    return {"calls": calls_out, "topics": topics_out}
```

- [ ] **Step 2: Add the endpoint to `backend/routers/topics.py`**

Add the import at the top (update the existing import line):

```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, TopicUpdate,
)
```

Append the route after the existing `list_topics` endpoint:

```python
@router.get("/projects/{project_id}/topics/timeline")
def timeline(project_id: str):
    logger.info(f"📥 [Topics] Timeline requested: project={project_id}")
    db = get_client()
    result = list_topics_timeline(project_id, db)
    logger.info(
        f"✅ [Topics] Timeline returned {len(result['calls'])} calls, "
        f"{len(result['topics'])} topics"
    )
    return result
```

- [ ] **Step 3: Verify the server starts without error**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 -m uvicorn backend.main:app --reload --port 8001 &
sleep 3
curl -s http://localhost:8001/api/projects/test-id/topics/timeline | python3 -m json.tool
kill %1
```

Expected: JSON with `{"calls": [], "topics": []}` (empty project) — no 500 error.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] feat: add list_topics_timeline service + GET endpoint"
```

---

## Task 2: Backend Tests

**Files:**
- Create: `backend/tests/test_topics_timeline.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_topics_timeline.py`:

```python
"""
Tests for GET /api/projects/{project_id}/topics/timeline

Mock chain for list_topics_timeline:
  db.table("calls").select(...).eq(...).order(...).execute()   → calls
  db.table("topics").select(...).eq(...).eq(...).execute()     → topics
  db.table("topic_updates").select(...).in_(...).execute()     → updates

We patch get_client in the ROUTER module (backend.routers.topics) and the
SERVICE module (backend.services.topics_service) separately because the
endpoint passes the db instance through; only the service import matters here.
"""

from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from backend.main import app

client = TestClient(app)

PROJECT_ID = "proj-timeline"
CALL_1 = "call-001"
CALL_2 = "call-002"
TOPIC_1 = "topic-001"


def _make_db(calls_data, topics_data, updates_data):
    """
    Build a mock Supabase client that returns the given data for the
    three sequential queries in list_topics_timeline.

    Query order:
      1. table("calls").select(...).eq(...).order(...).execute()
      2. table("topics").select(...).eq(...).eq(...).execute()
      3. table("topic_updates").select(...).in_(...).execute()
    """
    mc = MagicMock()

    calls_chain = MagicMock()
    calls_chain.execute.return_value = MagicMock(data=calls_data)
    calls_chain.eq.return_value = calls_chain
    calls_chain.order.return_value = calls_chain
    calls_chain.select.return_value = calls_chain

    topics_chain = MagicMock()
    topics_chain.execute.return_value = MagicMock(data=topics_data)
    topics_chain.eq.return_value = topics_chain
    topics_chain.select.return_value = topics_chain

    updates_chain = MagicMock()
    updates_chain.execute.return_value = MagicMock(data=updates_data)
    updates_chain.in_.return_value = updates_chain
    updates_chain.select.return_value = updates_chain

    def table_side_effect(name):
        if name == "calls":
            return calls_chain
        if name == "topics":
            return topics_chain
        if name == "topic_updates":
            return updates_chain
        return MagicMock()

    mc.table.side_effect = table_side_effect
    return mc


class TestTopicsTimeline:

    def test_timeline_no_topics(self):
        """Empty project: two calls, no topics → calls populated, topics empty."""
        mc = _make_db(
            calls_data=[
                {"id": CALL_1, "title": "Kickoff", "kanban_stage": "done", "created_at": "2026-04-01T10:00:00Z"},
                {"id": CALL_2, "title": "Review", "kanban_stage": "transcript", "created_at": "2026-04-02T10:00:00Z"},
            ],
            topics_data=[],
            updates_data=[],
        )
        with (
            patch("backend.routers.topics.get_client", return_value=mc),
            patch("backend.services.topics_service.get_client", return_value=mc),
        ):
            r = client.get(f"/api/projects/{PROJECT_ID}/topics/timeline")

        assert r.status_code == 200
        data = r.json()
        assert len(data["calls"]) == 2
        assert data["calls"][0]["number"] == 1
        assert data["calls"][1]["number"] == 2
        assert data["topics"] == []

    def test_timeline_new_and_not_discussed(self):
        """
        Topic raised in Call 1. Call 2 has no update for it.
        → Call 1 cell: type='new', Call 2 cell: type='not_discussed'
        """
        mc = _make_db(
            calls_data=[
                {"id": CALL_1, "title": "Kickoff", "kanban_stage": "done", "created_at": "2026-04-01T10:00:00Z"},
                {"id": CALL_2, "title": "Review", "kanban_stage": "done", "created_at": "2026-04-02T10:00:00Z"},
            ],
            topics_data=[
                {"id": TOPIC_1, "name": "Pricing", "first_raised_call_id": CALL_1},
            ],
            updates_data=[
                {
                    "topic_id": TOPIC_1, "call_id": CALL_1,
                    "summary": "Client asked about pricing.",
                    "follow_up_items": ["Send quote"], "decisions": [],
                    "status": "open", "owner": "Us", "sentiment": "neutral",
                },
            ],
        )
        with (
            patch("backend.routers.topics.get_client", return_value=mc),
            patch("backend.services.topics_service.get_client", return_value=mc),
        ):
            r = client.get(f"/api/projects/{PROJECT_ID}/topics/timeline")

        assert r.status_code == 200
        data = r.json()
        topic = data["topics"][0]
        assert topic["name"] == "Pricing"
        assert topic["call_updates"][CALL_1]["type"] == "new"
        assert topic["call_updates"][CALL_1]["summary"] == "Client asked about pricing."
        assert topic["call_updates"][CALL_2]["type"] == "not_discussed"

    def test_timeline_followed_up_and_absent(self):
        """
        Topic raised in Call 2 (not Call 1).
        → Call 1 key is absent from call_updates (topic didn't exist).
        → Call 2 cell: type='new', Call 3 cell (has update): type='followed_up'.
        """
        CALL_3 = "call-003"
        mc = _make_db(
            calls_data=[
                {"id": CALL_1, "title": "Kickoff", "kanban_stage": "done", "created_at": "2026-04-01T10:00:00Z"},
                {"id": CALL_2, "title": "Month 2", "kanban_stage": "done", "created_at": "2026-04-02T10:00:00Z"},
                {"id": CALL_3, "title": "Month 3", "kanban_stage": "done", "created_at": "2026-04-03T10:00:00Z"},
            ],
            topics_data=[
                {"id": TOPIC_1, "name": "Budget", "first_raised_call_id": CALL_2},
            ],
            updates_data=[
                {
                    "topic_id": TOPIC_1, "call_id": CALL_2,
                    "summary": "Budget concern raised.",
                    "follow_up_items": [], "decisions": [],
                    "status": "open", "owner": "Client", "sentiment": "concern",
                },
                {
                    "topic_id": TOPIC_1, "call_id": CALL_3,
                    "summary": "Budget approved.",
                    "follow_up_items": [], "decisions": ["Approved Q2 budget"],
                    "status": "resolved", "owner": "Both", "sentiment": "positive",
                },
            ],
        )
        with (
            patch("backend.routers.topics.get_client", return_value=mc),
            patch("backend.services.topics_service.get_client", return_value=mc),
        ):
            r = client.get(f"/api/projects/{PROJECT_ID}/topics/timeline")

        assert r.status_code == 200
        data = r.json()
        topic = data["topics"][0]
        assert CALL_1 not in topic["call_updates"]           # absent — topic didn't exist
        assert topic["call_updates"][CALL_2]["type"] == "new"
        assert topic["call_updates"][CALL_3]["type"] == "followed_up"
        assert topic["call_updates"][CALL_3]["decisions"] == ["Approved Q2 budget"]
        # Current state reflects latest update (Call 3)
        assert topic["status"] == "resolved"
        assert topic["sentiment"] == "positive"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 -m pytest backend/tests/test_topics_timeline.py -v
```

Expected: 3 FAILED (ImportError or AttributeError — `list_topics_timeline` not imported yet in router, or mock chain doesn't match).

- [ ] **Step 3: Run tests again after Task 1 is complete**

```bash
python3 -m pytest backend/tests/test_topics_timeline.py -v
```

Expected:
```
PASSED test_timeline_no_topics
PASSED test_timeline_new_and_not_discussed
PASSED test_timeline_followed_up_and_absent
3 passed
```

- [ ] **Step 4: Run full backend test suite to verify no regressions**

```bash
python3 -m pytest backend/tests/ -v
```

Expected: All previously passing tests still pass.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-8] test: add TopicsTimeline backend tests (3 passing)"
```

---

## Task 3: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add timeline types to `frontend/src/types/index.ts`**

Append after the existing `CallFile` interface (end of file):

```typescript
// ── Topics Timeline ─────────────────────────────────────────────────────────

/** One classified cell in the timeline grid */
export interface TimelineCell {
  type: "new" | "followed_up" | "not_discussed";
  summary?: string | null;
  follow_up_items?: string[];
  decisions?: string[];
  status?: TopicStatus | null;
  owner?: TopicOwner | null;
  sentiment?: TopicSentiment | null;
}

/** One topic row in the timeline grid */
export interface TimelineTopic {
  topic_id: string;
  name: string;
  status: TopicStatus;
  owner: TopicOwner;
  sentiment: TopicSentiment;
  first_raised_call_id: string | null;
  /** Keys are call IDs. Absent key = topic didn't exist at that call. */
  call_updates: Record<string, TimelineCell>;
}

/** Full response from GET /projects/{id}/topics/timeline */
export interface TopicsTimelineData {
  calls: {
    id: string;
    title: string;
    number: number;
    kanban_stage: string;
  }[];
  topics: TimelineTopic[];
}
```

- [ ] **Step 2: Add `topicsAPI.timeline` to `frontend/src/api/client.ts`**

Find the `topicsAPI` export block. Replace the closing `};` with:

```typescript
  timeline: (projectId: string) =>
    proxyFetch<import("@/types").TopicsTimelineData>(
      `/api/projects/${projectId}/topics/timeline`
    ),
};
```

(i.e. add the `timeline` method before the final closing `};` of the `topicsAPI` object)

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add TopicsTimeline types and topicsAPI.timeline"
```

---

## Task 4: `TopicsTimeline` Component

**Files:**
- Create: `frontend/src/components/TopicsTimeline.tsx`
- Modify: `frontend/app/projects/[id]/board/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/TopicsTimeline.tsx`**

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  TopicsTimelineData,
  TimelineTopic,
  TimelineCell,
  TopicStatus,
  TopicSentiment,
} from "@/types";

type Props = { projectId: string };

// ── Style constants ──────────────────────────────────────────────────────────

const BADGE: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  padding: "2px 6px",
  borderRadius: 3,
  whiteSpace: "nowrap",
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
  open: "Open",
  in_progress: "In Progress",
  resolved: "Resolved",
};

const CELL_TYPE_STYLE: Record<
  "new" | "followed_up" | "not_discussed",
  React.CSSProperties
> = {
  new:           { background: "#fff7ed", borderLeft: "3px solid #f97316" },
  followed_up:   { background: "#eff6ff", borderLeft: "3px solid #3b82f6" },
  not_discussed: { background: "#f8f9fa" },
};

const CELL_BADGE_STYLE: Record<"new" | "followed_up", React.CSSProperties> = {
  new:         { ...BADGE, background: "#f97316", color: "#fff" },
  followed_up: { ...BADGE, background: "#3b82f6", color: "#fff" },
};

const COL_WIDTH = 160;
const LEFT_COL_WIDTH = 220;

// ── Helpers ──────────────────────────────────────────────────────────────────

function truncate(s: string, max: number) {
  return s.length <= max ? s : s.slice(0, max - 1) + "…";
}

// ── Sub-components ───────────────────────────────────────────────────────────

function CellContent({ cell }: { cell: TimelineCell }) {
  if (cell.type === "not_discussed") {
    return (
      <span style={{ color: "#adb5bd", fontSize: 13, fontWeight: 500 }}>—</span>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={CELL_BADGE_STYLE[cell.type]}>
        {cell.type === "new" ? "✦ New" : "Updated"}
      </span>
      {cell.summary && (
        <p
          style={{
            margin: 0,
            fontSize: 11,
            color: "#172b4d",
            lineHeight: 1.4,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {cell.summary}
        </p>
      )}
      {cell.follow_up_items && cell.follow_up_items.length > 0 && (
        <span style={{ fontSize: 10, color: "#5e6c84" }}>
          {cell.follow_up_items.length} follow-up
          {cell.follow_up_items.length > 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}

function TopicRow({
  topic,
  callIds,
  isResolved,
}: {
  topic: TimelineTopic;
  callIds: string[];
  isResolved: boolean;
}) {
  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "stretch",
    borderBottom: "1px solid #dfe1e6",
    opacity: isResolved ? 0.65 : 1,
    minHeight: 64,
  };

  const leftCellStyle: React.CSSProperties = {
    width: LEFT_COL_WIDTH,
    minWidth: LEFT_COL_WIDTH,
    padding: "10px 12px",
    background: "#fff",
    position: "sticky",
    left: 0,
    zIndex: 1,
    borderRight: "1px solid #dfe1e6",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    justifyContent: "center",
  };

  return (
    <div style={rowStyle}>
      {/* Fixed left column */}
      <div style={leftCellStyle}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "#172b4d",
            lineHeight: 1.3,
          }}
        >
          {topic.name}
        </span>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          <span style={{ ...BADGE, ...STATUS_STYLE[topic.status] }}>
            {STATUS_LABEL[topic.status]}
          </span>
          {topic.sentiment !== "neutral" && (
            <span style={{ ...BADGE, ...SENT_STYLE[topic.sentiment] }}>
              {topic.sentiment}
            </span>
          )}
          <span
            style={{
              ...BADGE,
              background: "#f4f5f7",
              color: "#5e6c84",
            }}
          >
            {topic.owner}
          </span>
        </div>
      </div>

      {/* One cell per call */}
      {callIds.map((callId) => {
        const cell = topic.call_updates[callId];
        const cellStyle: React.CSSProperties = {
          width: COL_WIDTH,
          minWidth: COL_WIDTH,
          padding: "10px 12px",
          borderRight: "1px solid #dfe1e6",
          display: "flex",
          alignItems: "center",
          ...(cell ? CELL_TYPE_STYLE[cell.type] : { background: "#fafbfc" }),
        };

        return (
          <div key={callId} style={cellStyle}>
            {cell ? <CellContent cell={cell} /> : null}
          </div>
        );
      })}
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function TopicsTimeline({ projectId }: Props) {
  const [data, setData] = useState<TopicsTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Fetching topics timeline", {
        component: "TopicsTimeline",
        data: { projectId },
      });
      const result = await topicsAPI.timeline(projectId);
      setData(result);
    } catch (err) {
      logger.error("Failed to load topics timeline", {
        component: "TopicsTimeline",
        data: err,
      });
      setError("Failed to load topics timeline.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
        }}
      >
        <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
        <button
          onClick={load}
          style={{
            fontSize: 13,
            color: "#0052cc",
            background: "none",
            border: "none",
            cursor: "pointer",
            textDecoration: "underline",
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.topics.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p style={{ fontSize: 13, color: "#5e6c84" }}>
          {data && data.calls.length === 0
            ? "No calls yet."
            : "No topics extracted yet."}
        </p>
      </div>
    );
  }

  const callIds = data.calls.map((c) => c.id);

  return (
    <div
      style={{
        flex: 1,
        overflowX: "auto",
        overflowY: "auto",
        background: "#fff",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "stretch",
          borderBottom: "2px solid #dfe1e6",
          position: "sticky",
          top: 0,
          zIndex: 2,
          background: "#f4f5f7",
        }}
      >
        {/* Left column header */}
        <div
          style={{
            width: LEFT_COL_WIDTH,
            minWidth: LEFT_COL_WIDTH,
            padding: "8px 12px",
            background: "#f4f5f7",
            position: "sticky",
            left: 0,
            zIndex: 3,
            borderRight: "1px solid #dfe1e6",
            fontSize: 11,
            fontWeight: 700,
            color: "#5e6c84",
            textTransform: "uppercase",
            display: "flex",
            alignItems: "center",
          }}
        >
          Topic
        </div>

        {/* One header cell per call */}
        {data.calls.map((call) => (
          <div
            key={call.id}
            style={{
              width: COL_WIDTH,
              minWidth: COL_WIDTH,
              padding: "8px 12px",
              borderRight: "1px solid #dfe1e6",
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <span
              style={{ fontSize: 11, fontWeight: 700, color: "#172b4d" }}
            >
              Call {call.number}
            </span>
            <span
              style={{
                fontSize: 10,
                color: "#5e6c84",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={call.title}
            >
              {truncate(call.title, 22)}
            </span>
          </div>
        ))}
      </div>

      {/* Topic rows */}
      {data.topics.map((topic) => (
        <TopicRow
          key={topic.topic_id}
          topic={topic}
          callIds={callIds}
          isResolved={topic.status === "resolved"}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Update `frontend/app/projects/[id]/board/page.tsx`**

Replace the import:
```typescript
import TopicsDashboard from "@/components/TopicsDashboard";
```
with:
```typescript
import TopicsTimeline from "@/components/TopicsTimeline";
```

Replace the render call:
```typescript
        <TopicsDashboard projectId={projectId} />
```
with:
```typescript
        <TopicsTimeline projectId={projectId} />
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Verify the page loads in dev mode**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npm run dev &
sleep 5
```

Open `http://localhost:3000` → navigate to a project → Board → Topics tab. Expected:
- Grid renders with sticky left column
- Call columns scroll horizontally
- Resolved topics at 65% opacity
- Empty state message if no topics

- [ ] **Step 5: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-8] feat: add TopicsTimeline component, replace TopicsDashboard on Board"
```

---

## Self-review checklist (run before marking Epic 8 complete)

- [ ] `GET /projects/{id}/topics/timeline` returns correct JSON for empty project (calls populated, topics `[]`)
- [ ] Absent cells (topic didn't exist at call) are omitted from `call_updates` — not `null`, not `not_discussed`
- [ ] `not_discussed` cells contain only `{"type": "not_discussed"}`
- [ ] `type="new"` only on the call matching `first_raised_call_id`
- [ ] `type="followed_up"` on subsequent calls that have a `topic_update` row
- [ ] Current `status/owner/sentiment` on the topic row reflects the latest call's update
- [ ] 3 backend tests pass
- [ ] TypeScript compiles with no errors
- [ ] Left column is sticky (does not scroll horizontally)
- [ ] Header row is sticky (does not scroll vertically)
- [ ] Resolved topic rows render at 65% opacity
- [ ] Empty state shown when no topics or no calls
