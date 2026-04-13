# EPIC-7: Two-Step Topic Extraction + New Kanban Stages — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-shot biased topic extraction with a two-step pipeline (extract call independently → match against project topics), add `call_topics` and `project_topics` kanban stages, and inject project topic context into artifact generation.

**Architecture:** Step 1 extracts topics from the transcript only (no previous context, no bias). Step 2 receives the Step 1 flat list + accumulated project topics and runs a second LLM call to classify into 3 buckets. Frontend holds Step 1 results in state and passes them to Step 2. Call 1 auto-advances. Two new React components handle the two new stages.

**Tech Stack:** FastAPI, supabase-py, Next.js 15 App Router, React 19, TypeScript, inline styles.

**Context files to read before starting:**
- `backend/services/topics_service.py` — current extraction logic, `_get_previous_topics`, `save_topics`, `validate_call`
- `backend/routers/topics.py` — current endpoints
- `backend/routers/calls.py` — STAGE_ORDER, advance_stage
- `backend/routers/artifacts.py` — SSE stream endpoint, `generate_artifact` call signature
- `frontend/src/types/index.ts` — KanbanStage type
- `frontend/src/components/KanbanBoard.tsx` — STAGES array, getCellState
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — stage routing
- `frontend/src/api/client.ts` — topicsAPI

---

## File Map

| File | Action | What changes |
|---|---|---|
| `backend/database/migrations/011_two_step_topics_stages.sql` | Create | DB constraint + data migration |
| `backend/routers/calls.py` | Modify | STAGE_ORDER updated |
| `backend/services/topics_service.py` | Modify | Add `extract_call_topics`, `aggregate_topics`, `get_project_topics_context` |
| `backend/routers/topics.py` | Modify | Add 2 new endpoints |
| `backend/routers/artifacts.py` | Modify | Inject project topics context in SSE stream |
| `backend/tests/test_topics.py` | Modify | Add tests for new endpoints |
| `backend/tests/test_artifacts.py` | Modify | Add context injection test |
| `frontend/src/types/index.ts` | Modify | KanbanStage + AggregateResult |
| `frontend/src/api/client.ts` | Modify | extractCall, aggregate |
| `frontend/src/components/KanbanBoard.tsx` | Modify | 5-column STAGES, updated getCellState |
| `frontend/src/components/CallTopicsStage.tsx` | Create | call_topics stage UI |
| `frontend/src/components/ProjectTopicsStage.tsx` | Create | project_topics stage UI |
| `frontend/app/projects/[id]/calls/[call_id]/page.tsx` | Modify | Route new stages |

---

## Task 1: DB Migration — new stage values

**Files:**
- Create: `backend/database/migrations/011_two_step_topics_stages.sql`
- Modify: `backend/routers/calls.py`

- [ ] **Step 1: Write the migration file**

Create `backend/database/migrations/011_two_step_topics_stages.sql`:

```sql
-- 011_two_step_topics_stages.sql
-- Run in Supabase Dashboard → SQL Editor → New query
--
-- Replaces the single 'topics' kanban stage with two stages:
--   call_topics     — Step 1: extract topics from this call only (unbiased)
--   project_topics  — Step 2: match against accumulated project topics (3-bucket review)

-- 1. Drop old constraint
ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_kanban_stage_check;

-- 2. Add new constraint with both new stage values
ALTER TABLE calls
  ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN ('transcript','call_topics','project_topics','artifacts','done'));

-- 3. Migrate existing rows at 'topics' → 'call_topics'
--    (they haven't completed topics review yet, so they restart at Step 1)
UPDATE calls SET kanban_stage = 'call_topics' WHERE kanban_stage = 'topics';
```

- [ ] **Step 2: Run the migration in Supabase Dashboard → SQL Editor**

Paste and execute the SQL above. Verify: no errors, affected rows shown for the UPDATE.

- [ ] **Step 3: Update STAGE_ORDER in `backend/routers/calls.py`**

Find line:
```python
STAGE_ORDER = ["transcript", "topics", "artifacts", "done"]
```

Replace with:
```python
STAGE_ORDER = ["transcript", "call_topics", "project_topics", "artifacts", "done"]
```

- [ ] **Step 4: Write the failing test**

In `backend/tests/test_calls.py`, find `MOCK_CALL` and ensure `kanban_stage` is `"call_topics"` (not `"topics"`). Also update any test that references stage `"topics"` to use `"call_topics"`.

Search for all occurrences of `"topics"` stage in test_calls.py:
```bash
grep -n '"topics"' backend/tests/test_calls.py
```

Update each one: `"topics"` → `"call_topics"` where it refers to the kanban stage.

- [ ] **Step 5: Run backend tests to verify they pass**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 -m pytest backend/tests/test_calls.py -v
```

Expected: all pass (stage name updated, no other changes)

- [ ] **Step 6: Update TypeScript KanbanStage type**

In `frontend/src/types/index.ts`, find:
```typescript
export type KanbanStage = "transcript" | "topics" | "artifacts" | "done";
```

Replace with:
```typescript
export type KanbanStage = "transcript" | "call_topics" | "project_topics" | "artifacts" | "done";
```

- [ ] **Step 7: Update KanbanBoard.tsx — 5 columns**

In `frontend/src/components/KanbanBoard.tsx`, replace:

```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Transcript" },
  { key: "topics",     label: "Topics"     },
  { key: "artifacts",  label: "Artifacts"  },
  { key: "done",       label: "Done"       },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "topics", "artifacts", "done"];
```

With:

```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript",     label: "Transcript"      },
  { key: "call_topics",    label: "Call Topics"     },
  { key: "project_topics", label: "Project Topics"  },
  { key: "artifacts",      label: "Artifacts"       },
  { key: "done",           label: "Done"            },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "call_topics", "project_topics", "artifacts", "done"];
```

Also update `getCellState` — the "locked" rule currently references `"artifacts"`. Keep it the same (artifacts locked if prev call not done); the new stages are never locked:

```typescript
function getCellState(
  call: Call,
  stageKey: KanbanStage,
  prevCallDone: boolean
): CellState {
  const callIdx  = STAGE_INDEX[call.kanban_stage];
  const stageIdx = STAGE_INDEX[stageKey];

  if (callIdx > stageIdx) return "done";
  if (callIdx === stageIdx) {
    if (stageKey === "done" && call.is_locked) return "done";
    return "active";
  }

  // Artifacts and beyond locked until previous call is fully done
  if ((stageKey === "artifacts" || stageKey === "done") && !prevCallDone) {
    return "locked";
  }
  return "pending";
}
```

- [ ] **Step 8: Update page.tsx stage routing**

In `frontend/app/projects/[id]/calls/[call_id]/page.tsx`, find the stage routing block that handles `call.kanban_stage === "topics"`. Replace `"topics"` with `"call_topics"` in all routing/conditional logic. Add `"project_topics"` as a new case (placeholder component for now — will be replaced in Task 5).

Search for `topics` in the file:
```bash
grep -n "topics" frontend/app/projects/\[id\]/calls/\[call_id\]/page.tsx
```

For each stage check `=== "topics"`, change to `=== "call_topics"`.

- [ ] **Step 9: Verify TypeScript compiles**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 10: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-7] feat: add call_topics + project_topics kanban stages (Story 7.1)" \
  "backend/database/migrations/011_two_step_topics_stages.sql" \
  "backend/routers/calls.py" \
  "frontend/src/types/index.ts" \
  "frontend/src/components/KanbanBoard.tsx" \
  "frontend/app/projects/[id]/calls/[call_id]/page.tsx"
```

---

## Task 2: Step 1 — `extract_call_topics` service + endpoint

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/routers/topics.py`
- Modify: `backend/tests/test_topics.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_topics.py`:

```python
class TestExtractCallTopics(unittest.TestCase):

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("backend.services.topics_service.get_client")
    @patch("backend.services.topics_service._call_llm")
    def test_extract_call_topics_happy_path(self, mock_llm, mock_gc):
        """Returns flat list of topics from transcript only."""
        db = MagicMock()
        mock_gc.return_value = db
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1", "transcript": "We discussed the budget and timeline."}
        ]
        db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"default_llm": "groq"}]
        mock_llm.return_value = asyncio.coroutine(lambda: [
            {"name": "Budget", "summary": "Discussed Q2 budget", "follow_up_items": [],
             "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral"}
        ])()

        result = self._run(extract_call_topics("call-1"))

        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["name"], "Budget")

    @patch("backend.services.topics_service.get_client")
    def test_extract_call_topics_no_transcript(self, mock_gc):
        """Raises ValueError when transcript is empty."""
        db = MagicMock()
        mock_gc.return_value = db
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1", "transcript": ""}
        ]
        with self.assertRaises(ValueError) as ctx:
            self._run(extract_call_topics("call-1"))
        self.assertEqual(str(ctx.exception), "no_transcript")
```

Also add `extract_call_topics` to the import at top of `test_topics.py`:

```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, extract_call_topics, TopicUpdate,
)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest backend/tests/test_topics.py::TestExtractCallTopics -v
```

Expected: `ImportError: cannot import name 'extract_call_topics'`

- [ ] **Step 3: Implement `extract_call_topics` in `backend/services/topics_service.py`**

Add after `extract_topics` / `_extract_topics_impl` (around line 265):

```python
async def extract_call_topics(call_id: str) -> list[dict]:
    """
    Step 1: extract topics from this call's transcript ONLY.
    No previous project topics in context — eliminates extraction bias.
    Returns a flat list of topic dicts (not saved to DB).
    """
    db = get_client()

    call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    transcript = (call_row[0]["transcript"] or "").strip()
    if not transcript:
        raise ValueError("no_transcript")

    project_id = call_row[0]["project_id"]
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db)
    if stored_llm is None:
        proj_rows = db.table("projects").select("default_llm").eq("id", project_id).execute().data
        stored_llm = proj_rows[0]["default_llm"] if proj_rows else "groq"
    llm = stored_llm or "groq"

    prompt = (
        (f"{stored_prompt}\n\n" if stored_prompt else "Extract all key business topics from this call.\n\n")
        + f"Return a JSON array where each element matches this exact schema:\n{_TOPIC_SCHEMA}\n\n"
        + f"Transcript:\n{transcript}"
    )

    raw = await _call_llm(prompt, llm)
    # Flatten if LLM returned a dict (shouldn't happen with flat-list prompt, but safe)
    if isinstance(raw, dict):
        flat: list[dict] = []
        for v in raw.values():
            if isinstance(v, list):
                flat.extend(v)
        return flat
    return raw if isinstance(raw, list) else []
```

- [ ] **Step 4: Add the endpoint to `backend/routers/topics.py`**

Add the import update at top:
```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, extract_call_topics, TopicUpdate,
)
```

Add the endpoint after the `extract` endpoint:

```python
@router.post("/calls/{call_id}/topics/extract_call")
async def extract_call(call_id: str):
    """Step 1: extract topics from this call's transcript only (no previous context)."""
    logger.info(f"📥 [Topics] Step-1 extract requested: call={call_id}")
    try:
        result = await extract_call_topics(call_id)
        logger.info(f"✅ [Topics] Step-1 extracted {len(result)} topics")
        return result
    except ValueError as e:
        msg = str(e)
        if msg == "no_transcript":
            raise HTTPException(status_code=422, detail="Call has no transcript")
        raise HTTPException(status_code=404, detail=msg)
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-1 extraction failed: {e}")
        raise HTTPException(status_code=500, detail="Topic extraction failed")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest backend/tests/test_topics.py::TestExtractCallTopics -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Run full backend suite**

```bash
python3 -m pytest backend/tests/ -v --tb=short 2>&1 | tail -5
```

Expected: all existing tests still pass

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: add extract_call_topics endpoint — Step 1 unbiased extraction (Story 7.2)" \
  "backend/services/topics_service.py" \
  "backend/routers/topics.py" \
  "backend/tests/test_topics.py"
```

---

## Task 3: Step 2 — `aggregate_topics` service + endpoint

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/routers/topics.py`
- Modify: `backend/tests/test_topics.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_topics.py`:

```python
class TestAggregateTopics(unittest.TestCase):

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("backend.services.topics_service.get_client")
    @patch("backend.services.topics_service.save_topics")
    def test_aggregate_call1_auto_advances(self, mock_save, mock_gc):
        """Call 1: no previous topics → saves all as new, returns auto_advanced=True."""
        db = MagicMock()
        mock_gc.return_value = db
        # call row
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1"}
        ]
        # _get_previous_topics → no topics
        topics_q = db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute
        topics_q.return_value.data = []
        # done calls count
        done_q = (db.table.return_value.select.return_value.eq.return_value
                  .eq.return_value.execute)
        done_q.return_value.data = []
        # advance stage
        db.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [{}]
        mock_save.return_value = {"saved": 1}

        call_topics = [{"name": "Budget", "summary": "Q2 budget", "follow_up_items": [],
                        "decisions": [], "status": "open", "owner": "Us", "sentiment": "neutral"}]

        result = self._run(aggregate_topics("call-1", call_topics))

        self.assertTrue(result["auto_advanced"])
        self.assertEqual(result["call_number"], 1)

    @patch("backend.services.topics_service.get_client")
    @patch("backend.services.topics_service._call_llm")
    def test_aggregate_call2_returns_buckets(self, mock_llm, mock_gc):
        """Call 2: previous topics exist → runs LLM, returns 3 buckets, advances to project_topics."""
        db = MagicMock()
        mock_gc.return_value = db
        # call row
        db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"project_id": "proj-1"}
        ]
        # _get_previous_topics → one topic
        prev_topic = {"topic_id": "t-1", "name": "Budget", "calls_open": 1,
                      "summary": "old summary", "follow_up_items": [], "decisions": [],
                      "status": "open", "owner": "Us", "sentiment": "neutral"}
        # done calls
        done_q = (db.table.return_value.select.return_value.eq.return_value
                  .eq.return_value.execute)
        done_q.return_value.data = [{"id": "call-0"}]

        # Mock _get_previous_topics via db.table chain
        # (simplified — the real mock chain is complex; use patch instead)
        async def fake_llm(prompt, llm):
            return {
                "followed_up": [{"name": "Budget", "summary": "Updated", "follow_up_items": [],
                                 "decisions": [], "status": "in_progress", "owner": "Us", "sentiment": "neutral"}],
                "not_discussed": [],
                "new_topics": [{"name": "Timeline", "summary": "New topic", "follow_up_items": [],
                                "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"}],
            }
        mock_llm.side_effect = fake_llm

        with patch("backend.services.topics_service._get_previous_topics", return_value=[prev_topic]):
            with patch("backend.services.topics_service._get_topics_prompt", return_value=(None, "groq")):
                result = self._run(aggregate_topics("call-1", [
                    {"name": "Budget", "summary": "Budget discussed", "follow_up_items": [],
                     "decisions": [], "status": "in_progress", "owner": "Us", "sentiment": "neutral"},
                    {"name": "Timeline", "summary": "New topic", "follow_up_items": [],
                     "decisions": [], "status": "open", "owner": "Client", "sentiment": "concern"},
                ]))

        self.assertNotIn("auto_advanced", result)
        self.assertIn("followed_up", result)
        self.assertIn("new_topics", result)
        self.assertEqual(result["followed_up"][0]["topic_id"], "t-1")  # _reattach_id worked
```

Also add `aggregate_topics` to the import:

```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, extract_call_topics,
    aggregate_topics, TopicUpdate,
)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest backend/tests/test_topics.py::TestAggregateTopics -v
```

Expected: ImportError

- [ ] **Step 3: Implement `aggregate_topics` in `backend/services/topics_service.py`**

Add after `extract_call_topics`:

```python
_AGGREGATE_SYSTEM = (
    "You are an expert at matching client call topics to an existing project topic list. "
    "Return ONLY valid JSON. No markdown, no explanation."
)

async def aggregate_topics(call_id: str, call_topics: list[dict]) -> dict:
    """
    Step 2: match call_topics (from Step 1) against accumulated project topics.

    Call 1 (no previous): saves all topics as new, advances stage to 'artifacts',
      returns {"auto_advanced": True, "call_number": 1}.

    Call 2+: runs LLM to classify into 3 buckets, advances stage to 'project_topics',
      returns {call_number, followed_up, not_discussed, new_topics}.
    """
    db = get_client()

    call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
    if not call_row:
        raise ValueError(f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]

    previous = _get_previous_topics(project_id, db)

    done_calls = (
        db.table("calls").select("id")
        .eq("project_id", project_id).eq("kanban_stage", "done")
        .execute().data
    )
    call_number = len(done_calls) + 1

    if not previous:
        # Call 1: auto-advance — save all as new topics and jump to artifacts
        new_topics = [
            TopicUpdate(**{**t, "topic_id": None, "disposition": None})
            for t in call_topics
        ]
        await save_topics(call_id, new_topics)
        db.table("calls").update({"kanban_stage": "artifacts"}).eq("id", call_id).execute()
        logger.info(f"✅ [Topics] Call 1 auto-advanced: saved {len(new_topics)} topics → artifacts")
        return {"auto_advanced": True, "call_number": 1}

    # Call 2+: LLM matching
    stored_prompt, stored_llm = _get_topics_prompt(project_id, db)
    if stored_llm is None:
        proj_rows = db.table("projects").select("default_llm").eq("id", project_id).execute().data
        stored_llm = proj_rows[0]["default_llm"] if proj_rows else "groq"
    llm = stored_llm or "groq"

    # Build previous topics context with history for semantic matching
    prev_context = [
        {
            "topic_id": t["topic_id"],
            "name": t["name"],
            "status": t["status"],
            "summary": t["summary"],
            "follow_up_items": t["follow_up_items"],
        }
        for t in previous
    ]

    prompt = (
        f"Match the new call topics to the existing project topics.\n\n"
        f"New call topics:\n{json.dumps(call_topics, indent=2)}\n\n"
        f"Existing project topics (with history):\n{json.dumps(prev_context, indent=2)}\n\n"
        f"Rules:\n"
        f"- If a new topic matches an existing one (same subject, possibly different wording): "
        f"put it in 'followed_up'. Use the existing topic name exactly. Update summary/status/follow_ups with new info.\n"
        f"- Existing topics not covered by any new topic: put in 'not_discussed' unchanged.\n"
        f"- New topics with no match: put in 'new_topics'.\n\n"
        f"Return JSON: {{\"followed_up\": [...], \"not_discussed\": [...], \"new_topics\": [...]}}\n"
        f"Each topic: {_TOPIC_SCHEMA}"
    )

    raw = await _call_llm(prompt, llm)

    # Re-attach topic_ids stripped by LLM
    prev_by_name = {t["name"].lower().strip(): t["topic_id"] for t in previous}

    def _reattach_id(topic: dict) -> dict:
        if not topic.get("topic_id"):
            key = topic.get("name", "").lower().strip()
            if key in prev_by_name:
                topic = {**topic, "topic_id": prev_by_name[key]}
        return topic

    if isinstance(raw, list):
        prev_names = {t["name"] for t in previous}
        followed_up = [_reattach_id(t) for t in raw if t["name"] in prev_names]
        not_discussed = [t for t in previous if t["name"] not in {x["name"] for x in raw}]
        new_topics_list = [t for t in raw if t["name"] not in prev_names]
    else:
        followed_up = [_reattach_id(t) for t in raw.get("followed_up", [])]
        not_discussed = [_reattach_id(t) for t in raw.get("not_discussed", [])]
        new_topics_list = raw.get("new_topics", [])

    # Advance to project_topics stage for user review
    db.table("calls").update({"kanban_stage": "project_topics"}).eq("id", call_id).execute()
    logger.info(f"✅ [Topics] Step-2 complete: {len(followed_up)} followed, "
                f"{len(not_discussed)} not discussed, {len(new_topics_list)} new → project_topics")

    return {
        "call_number": call_number,
        "followed_up": followed_up,
        "not_discussed": not_discussed,
        "new_topics": new_topics_list,
    }
```

- [ ] **Step 4: Add the endpoint to `backend/routers/topics.py`**

Update imports:
```python
from backend.services.topics_service import (
    extract_topics, save_topics, validate_call, generate_brief,
    list_project_topics, list_topics_timeline, extract_call_topics,
    aggregate_topics, TopicUpdate,
)
```

Add the endpoint after `extract_call`:

```python
class AggregatePayload(BaseModel):
    topics: list[dict]


@router.post("/calls/{call_id}/topics/aggregate")
async def aggregate(call_id: str, payload: AggregatePayload):
    """Step 2: match call topics against project topics → 3 buckets or auto-advance."""
    logger.info(f"📥 [Topics] Step-2 aggregate requested: call={call_id}, "
                f"input_topics={len(payload.topics)}")
    try:
        result = await aggregate_topics(call_id, payload.topics)
        if result.get("auto_advanced"):
            logger.info(f"✅ [Topics] Auto-advanced Call 1: {call_id}")
        else:
            total = sum(len(result.get(k, [])) for k in ("followed_up", "not_discussed", "new_topics"))
            logger.info(f"✅ [Topics] Step-2 returned {total} classified topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest backend/tests/test_topics.py::TestAggregateTopics -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Run full backend suite**

```bash
python3 -m pytest backend/tests/ -v --tb=short 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: add aggregate_topics endpoint — Step 2 LLM matching (Story 7.3)" \
  "backend/services/topics_service.py" \
  "backend/routers/topics.py" \
  "backend/tests/test_topics.py"
```

---

## Task 4: Artifact context — inject project topics

**Files:**
- Modify: `backend/services/topics_service.py`
- Modify: `backend/routers/artifacts.py`
- Modify: `backend/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_artifacts.py`, add:

```python
@patch("backend.routers.artifacts.get_client")
@patch("backend.routers.artifacts.generate_artifact")
@patch("backend.routers.artifacts.get_project_topics_context")
def test_artifact_stream_injects_project_context(mock_ctx, mock_gen, mock_gc):
    """SSE stream passes project topics context to generate_artifact."""
    db = MagicMock()
    mock_gc.return_value = db

    # call row with project_id
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "call-1", "transcript": "transcript text", "project_id": "proj-1"}
    ]
    # topic_updates (empty for simplicity)
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    # pending artifacts
    pending_q = (db.table.return_value.select.return_value.eq.return_value
                 .eq.return_value.execute)
    pending_q.return_value.data = [
        {"id": "art-1", "prompt_used": "Summarise", "mode": "claude"}
    ]

    mock_ctx.return_value = "=== Project Topics ===\n• Budget [open]"

    async def fake_gen(prompt, transcript, mode, topics=None):
        return "content"
    mock_gen.side_effect = fake_gen

    # Just verify get_project_topics_context was called
    response = client.get("/api/calls/call-1/artifacts/stream")
    mock_ctx.assert_called_once()
```

Also add the import at the top of `test_artifacts.py`:
```python
from backend.routers.artifacts import get_project_topics_context  # noqa: F401
```

Wait — `get_project_topics_context` will live in `topics_service.py` and be imported into `artifacts.py`. Patch it at the artifacts module level: `"backend.routers.artifacts.get_project_topics_context"`.

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest backend/tests/test_artifacts.py::test_artifact_stream_injects_project_context -v
```

Expected: ImportError or AttributeError (function not yet imported)

- [ ] **Step 3: Add `get_project_topics_context` to `backend/services/topics_service.py`**

Add after `list_project_topics`:

```python
def get_project_topics_context(project_id: str, db=None) -> str:
    """
    Build a compact summary of open/in_progress project topics for artifact context.
    Returns empty string if no open topics.
    """
    if db is None:
        db = get_client()
    previous = _get_previous_topics(project_id, db)
    open_topics = [t for t in previous if t.get("status") in ("open", "in_progress")]
    if not open_topics:
        return ""

    lines = ["=== Current Project Topics ==="]
    for t in open_topics:
        lines.append(
            f"\n• {t['name']} [{t['status']} / {t['owner']} / {t['sentiment']}]"
        )
        if t.get("summary"):
            lines.append(f"  Latest: {t['summary']}")
        for item in (t.get("follow_up_items") or [])[:3]:
            lines.append(f"  → {item}")
    return "\n".join(lines)
```

- [ ] **Step 4: Update `backend/routers/artifacts.py`**

Add import at top:
```python
from backend.services.topics_service import get_project_topics_context
```

In `stream_artifacts`, find the line that reads:
```python
transcript = call_result.data[0].get("transcript") or ""
```

Change the `select` to also fetch `project_id`:
```python
call_result = (
    supabase.table("calls")
    .select("id,transcript,project_id")
    .eq("id", call_id)
    .execute()
)
if not call_result.data:
    raise HTTPException(status_code=404, detail="Call not found")
transcript = call_result.data[0].get("transcript") or ""
project_id = call_result.data[0].get("project_id", "")
```

Then after the `call_topics` block (around line 187, after `except Exception: call_topics = None`), add:

```python
# Project-level open topics context (best-effort)
project_topics_context = ""
try:
    project_topics_context = get_project_topics_context(project_id, supabase)
except Exception:
    project_topics_context = ""
```

Finally, in `gen_one`, change the `generate_artifact` call to pass the project context. Find:
```python
content = await generate_artifact(prompt_used, transcript, artifact["mode"], topics=call_topics)
```

Replace with:
```python
# Combine transcript with project topic context for richer artifact generation
full_context = transcript
if project_topics_context:
    full_context = f"{transcript}\n\n{project_topics_context}"
content = await generate_artifact(prompt_used, full_context, artifact["mode"], topics=call_topics)
```

- [ ] **Step 5: Run the test**

```bash
python3 -m pytest backend/tests/test_artifacts.py::test_artifact_stream_injects_project_context -v
```

Expected: PASS

- [ ] **Step 6: Run full backend suite**

```bash
python3 -m pytest backend/tests/ -v --tb=short 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-7] feat: inject project topics context into artifact generation (Story 7.6)" \
  "backend/services/topics_service.py" \
  "backend/routers/artifacts.py" \
  "backend/tests/test_artifacts.py"
```

---

## Task 5: Frontend API client + types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add `AggregateResult` type to `frontend/src/types/index.ts`**

After `ExtractionResult` interface (around line 82), add:

```typescript
/** Response from POST /aggregate */
export interface AggregateResult {
  auto_advanced?: boolean;   // true = Call 1, stage already advanced to artifacts
  call_number: number;
  followed_up?: TopicData[];
  not_discussed?: TopicData[];
  new_topics?: TopicData[];
}
```

- [ ] **Step 2: Add `extractCall` and `aggregate` to `topicsAPI` in `frontend/src/api/client.ts`**

Also add `AggregateResult` to the type imports. Find the import line:
```typescript
import type { ... TopicData, TopicSavePayload, CallBrief ... } from "@/types";
```

Add `AggregateResult` to it.

Find `topicsAPI` and add two methods:

```typescript
export const topicsAPI = {
  // ... existing methods ...
  listForProject: (projectId: string) =>
    proxyFetch<TopicData[]>(`/api/projects/${projectId}/topics`),

  extractCall: (callId: string) =>
    proxyFetch<TopicData[]>(`/api/calls/${callId}/topics/extract_call`, {
      method: "POST",
    }),

  aggregate: (callId: string, topics: TopicData[]) =>
    proxyFetch<AggregateResult>(`/api/calls/${callId}/topics/aggregate`, {
      method: "POST",
      body: JSON.stringify({ topics }),
    }),
};
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
python3 scripts/git_ops.py commit "[EPIC-7] feat: add AggregateResult type and extractCall/aggregate API methods" \
  "frontend/src/types/index.ts" \
  "frontend/src/api/client.ts"
```

---

## Task 6: `CallTopicsStage` component

**Files:**
- Create: `frontend/src/components/CallTopicsStage.tsx`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/CallTopicsStage.tsx`**

```tsx
"use client";

import { useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, AggregateResult, TopicStatus, TopicOwner, TopicSentiment } from "@/types";

type Props = {
  call: Call;
  onAggregateComplete: (result: AggregateResult) => void;
  onAutoAdvanced: () => void;
};

const FIELD_STYLE: React.CSSProperties = {
  width: "100%", fontSize: 11, padding: "4px 6px", borderRadius: 4,
  border: "1px solid #dfe1e6", fontFamily: "inherit",
};

function TopicCard({
  topic,
  onChange,
}: {
  topic: TopicData;
  onChange: (updated: TopicData) => void;
}) {
  return (
    <div style={{
      background: "white", border: "1px solid #dfe1e6", borderRadius: 8,
      padding: 12, display: "flex", flexDirection: "column", gap: 8,
    }}>
      <input
        value={topic.name}
        onChange={(e) => onChange({ ...topic, name: e.target.value })}
        placeholder="Topic name"
        style={{ ...FIELD_STYLE, fontWeight: 600, fontSize: 13 }}
      />
      <textarea
        value={topic.summary}
        onChange={(e) => onChange({ ...topic, summary: e.target.value })}
        placeholder="Summary"
        rows={2}
        style={{ ...FIELD_STYLE, resize: "vertical" }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={topic.status}
          onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={topic.owner}
          onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="Us">Us</option>
          <option value="Client">Client</option>
          <option value="Both">Both</option>
        </select>
        <select
          value={topic.sentiment}
          onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="concern">Concern</option>
        </select>
      </div>
    </div>
  );
}

export default function CallTopicsStage({ call, onAggregateComplete, onAutoAdvanced }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExtract() {
    setExtracting(true);
    setError(null);
    try {
      logger.info("Extracting call topics (Step 1)", { component: "CallTopicsStage" });
      const result = await topicsAPI.extractCall(call.id);
      setTopics(result);
      setExtracted(true);
      logger.info(`Extracted ${result.length} topics`, { component: "CallTopicsStage" });
    } catch (err) {
      logger.error("Step 1 extraction failed", { component: "CallTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleContinue() {
    setAggregating(true);
    setError(null);
    try {
      logger.info("Aggregating topics (Step 2)", { component: "CallTopicsStage" });
      const result = await topicsAPI.aggregate(call.id, topics);
      if (result.auto_advanced) {
        logger.info("Call 1 auto-advanced to artifacts", { component: "CallTopicsStage" });
        onAutoAdvanced();
      } else {
        onAggregateComplete(result);
      }
    } catch (err) {
      logger.error("Step 2 aggregation failed", { component: "CallTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Aggregation failed");
    } finally {
      setAggregating(false);
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
          Call Topics
        </h2>
        <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
          Step 1 of 2 — Extract topics from this call only, without any previous context.
          Review and edit before continuing to match against project topics.
        </p>
      </div>

      {error && (
        <div style={{ background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19" }}>
          {error}
        </div>
      )}

      {!extracted ? (
        <button
          onClick={handleExtract}
          disabled={extracting}
          style={{
            alignSelf: "flex-start", padding: "10px 20px", borderRadius: 6,
            background: extracting ? "#f4f5f7" : "#0052cc", color: extracting ? "#97a0af" : "white",
            border: "none", cursor: extracting ? "default" : "pointer",
            fontSize: 13, fontWeight: 600,
          }}
        >
          {extracting ? "Extracting…" : "Extract this call's topics"}
        </button>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {topics.map((t, i) => (
              <TopicCard
                key={i}
                topic={t}
                onChange={(updated) => {
                  const next = [...topics];
                  next[i] = updated;
                  setTopics(next);
                }}
              />
            ))}
          </div>
          {topics.length === 0 && (
            <p style={{ fontSize: 12, color: "#97a0af" }}>No topics extracted. Try again or add topics manually.</p>
          )}
          <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
            <button
              onClick={() => { setExtracted(false); setTopics([]); }}
              style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                background: "white", color: "#5e6c84", fontSize: 12, cursor: "pointer" }}
            >
              Re-extract
            </button>
            <button
              onClick={handleContinue}
              disabled={aggregating || topics.length === 0}
              style={{
                padding: "8px 20px", borderRadius: 6, border: "none",
                background: aggregating || topics.length === 0 ? "#f4f5f7" : "#0052cc",
                color: aggregating || topics.length === 0 ? "#97a0af" : "white",
                fontSize: 13, fontWeight: 600,
                cursor: aggregating || topics.length === 0 ? "default" : "pointer",
              }}
            >
              {aggregating ? "Matching with project…" : "Continue →"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire `CallTopicsStage` into `page.tsx`**

In `frontend/app/projects/[id]/calls/[call_id]/page.tsx`:

1. Add import:
```typescript
import CallTopicsStage from "@/components/CallTopicsStage";
import type { AggregateResult } from "@/types";
```

2. Add state for aggregate result (near top of component, with other state):
```typescript
const [aggregateResult, setAggregateResult] = useState<AggregateResult | null>(null);
```

3. In the stage routing (where `call.kanban_stage` is checked), add/update the `call_topics` case:
```tsx
{call.kanban_stage === "call_topics" && (
  <CallTopicsStage
    call={call}
    onAggregateComplete={(result) => {
      setAggregateResult(result);
      loadCall(); // reload call — stage is now project_topics
    }}
    onAutoAdvanced={() => {
      loadCall(); // reload call — stage is now artifacts
    }}
  />
)}
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
python3 scripts/git_ops.py commit "[EPIC-7] feat: add CallTopicsStage component and wire into call page (Story 7.4)" \
  "frontend/src/components/CallTopicsStage.tsx" \
  "frontend/app/projects/[id]/calls/[call_id]/page.tsx"
```

---

## Task 7: `ProjectTopicsStage` component

**Files:**
- Create: `frontend/src/components/ProjectTopicsStage.tsx`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/ProjectTopicsStage.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call, TopicData, AggregateResult, TopicSavePayload, TopicDisposition,
  TopicStatus, TopicOwner, TopicSentiment,
} from "@/types";

type Props = {
  call: Call;
  initialResult: AggregateResult | null;  // from CallTopicsStage state; null = user navigated back
  onValidated: () => void;
};

const BADGE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};

// ── Topic card for 3-bucket view ──────────────────────────────────────────────

type BucketType = "followed_up" | "not_discussed" | "new_topics";

type EditableTopic = TopicData & {
  disposition?: TopicDisposition;
  _linkedTopicId?: string | null;
};

function BucketCard({
  topic,
  bucket,
  existingTopics,
  onChange,
  onLink,
  callIsLocked,
}: {
  topic: EditableTopic;
  bucket: BucketType;
  existingTopics: TopicData[];
  onChange: (t: EditableTopic) => void;
  onLink: (topicId: string, topicName: string) => void;
  callIsLocked: boolean;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [search, setSearch] = useState("");

  const filteredExisting = existingTopics.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase())
  );

  const FIELD: React.CSSProperties = {
    width: "100%", fontSize: 11, padding: "4px 6px", borderRadius: 4,
    border: "1px solid #dfe1e6", fontFamily: "inherit",
  };

  return (
    <div style={{
      background: "white", border: "1px solid #dfe1e6", borderRadius: 8, padding: 12,
      display: "flex", flexDirection: "column", gap: 8,
      opacity: callIsLocked ? 0.75 : 1,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <input
          value={topic.name}
          disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, name: e.target.value })}
          style={{ ...FIELD, fontWeight: 600, fontSize: 13, flex: 1 }}
        />
        {bucket === "new_topics" && !callIsLocked && (
          <button
            onClick={() => setShowPicker((v) => !v)}
            style={{ marginLeft: 8, fontSize: 10, padding: "3px 8px", borderRadius: 4,
              border: "1px solid #b3c6e8", background: "#e9f0ff", color: "#0052cc",
              cursor: "pointer", whiteSpace: "nowrap" }}
          >
            Link to existing →
          </button>
        )}
      </div>

      {showPicker && (
        <div style={{ border: "1px solid #dfe1e6", borderRadius: 6, padding: 8,
          background: "#fafbfc", display: "flex", flexDirection: "column", gap: 6 }}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search existing topics…"
            autoFocus
            style={{ ...FIELD }}
          />
          <div style={{ maxHeight: 140, overflowY: "auto" }}>
            {filteredExisting.length === 0 && (
              <p style={{ fontSize: 11, color: "#97a0af", padding: 4 }}>No matches</p>
            )}
            {filteredExisting.map((t) => (
              <button
                key={t.topic_id}
                onClick={() => {
                  if (t.topic_id) {
                    onLink(t.topic_id, t.name);
                    setShowPicker(false);
                    setSearch("");
                  }
                }}
                style={{ display: "block", width: "100%", textAlign: "left",
                  padding: "5px 8px", fontSize: 11, border: "none", background: "none",
                  cursor: "pointer", borderRadius: 4, color: "#172b4d" }}
              >
                {t.name}
              </button>
            ))}
          </div>
          <button onClick={() => setShowPicker(false)}
            style={{ fontSize: 10, color: "#97a0af", border: "none", background: "none",
              cursor: "pointer", alignSelf: "flex-start" }}>
            Cancel
          </button>
        </div>
      )}

      <textarea
        value={topic.summary}
        disabled={callIsLocked}
        onChange={(e) => onChange({ ...topic, summary: e.target.value })}
        rows={2}
        style={{ ...FIELD, resize: "vertical" }}
      />

      <div style={{ display: "flex", gap: 8 }}>
        <select value={topic.status} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select value={topic.owner} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="Us">Us</option>
          <option value="Client">Client</option>
          <option value="Both">Both</option>
        </select>
        <select value={topic.sentiment} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="concern">Concern</option>
        </select>
      </div>

      {bucket === "not_discussed" && !callIsLocked && (
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => onChange({ ...topic, disposition: "keep_as_is" })}
            style={{ flex: 1, padding: "5px", fontSize: 10, borderRadius: 4, cursor: "pointer",
              border: "1px solid", fontWeight: 600,
              background: topic.disposition === "keep_as_is" ? "#e9f0ff" : "white",
              borderColor: topic.disposition === "keep_as_is" ? "#0052cc" : "#dfe1e6",
              color: topic.disposition === "keep_as_is" ? "#0052cc" : "#5e6c84" }}>
            Keep as-is
          </button>
          <button
            onClick={() => onChange({ ...topic, disposition: "archive" })}
            style={{ flex: 1, padding: "5px", fontSize: 10, borderRadius: 4, cursor: "pointer",
              border: "1px solid", fontWeight: 600,
              background: topic.disposition === "archive" ? "#fff4e6" : "white",
              borderColor: topic.disposition === "archive" ? "#ff8b00" : "#dfe1e6",
              color: topic.disposition === "archive" ? "#974f0c" : "#5e6c84" }}>
            Archive
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ProjectTopicsStage({ call, initialResult, onValidated }: Props) {
  const [result, setResult] = useState<AggregateResult | null>(initialResult);
  const [followed, setFollowed] = useState<EditableTopic[]>([]);
  const [notDiscussed, setNotDiscussed] = useState<EditableTopic[]>([]);
  const [newTopics, setNewTopics] = useState<EditableTopic[]>([]);
  const [existingTopics, setExistingTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(!initialResult);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate buckets from result
  useEffect(() => {
    if (!result) return;
    setFollowed((result.followed_up ?? []).map((t) => ({ ...t })));
    setNotDiscussed((result.not_discussed ?? []).map((t) => ({ ...t, disposition: undefined })));
    setNewTopics((result.new_topics ?? []).map((t) => ({ ...t })));
  }, [result]);

  // Load existing project topics for "Link to existing" picker
  useEffect(() => {
    topicsAPI.listForProject(call.project_id)
      .then(setExistingTopics)
      .catch(() => {});
  }, [call.project_id]);

  // If no initialResult (user navigated back), re-run Step 1 + Step 2 automatically
  const reAggregate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Re-running Step 1+2 (state lost)", { component: "ProjectTopicsStage" });
      const step1 = await topicsAPI.extractCall(call.id);
      const step2 = await topicsAPI.aggregate(call.id, step1);
      setResult(step2);
    } catch (err) {
      logger.error("Re-aggregation failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Failed to load topics");
    } finally {
      setLoading(false);
    }
  }, [call.id]);

  useEffect(() => {
    if (!initialResult) {
      reAggregate();
    }
  }, [initialResult, reAggregate]);

  // "Link to existing" — move from new_topics to followed_up with matched topic_id
  function handleLink(newTopicIdx: number, topicId: string, topicName: string) {
    const linked = { ...newTopics[newTopicIdx], topic_id: topicId, name: topicName };
    setFollowed((prev) => [...prev, linked]);
    setNewTopics((prev) => prev.filter((_, i) => i !== newTopicIdx));
  }

  const unacknowledgedCount = notDiscussed.filter((t) => !t.disposition).length;
  const canValidate = !validating && unacknowledgedCount === 0 &&
    (followed.length + notDiscussed.length + newTopics.length) > 0;

  async function handleValidate() {
    setValidating(true);
    setError(null);
    try {
      const allTopics: TopicSavePayload[] = [
        ...followed.map((t) => ({ ...t, topic_id: t.topic_id ?? null, disposition: null })),
        ...notDiscussed.map((t) => ({
          ...t, topic_id: t.topic_id ?? null,
          disposition: (t.disposition ?? null) as TopicDisposition,
        })),
        ...newTopics.map((t) => ({ ...t, topic_id: null, disposition: null })),
      ];
      await topicsAPI.save(call.id, allTopics);
      await topicsAPI.validate(call.id);
      onValidated();
    } catch (err) {
      logger.error("Validate failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Matching topics with project history…</p>
    </div>
  );

  if (error && !result) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
      <button onClick={reAggregate} style={{ fontSize: 12, color: "#0052cc", textDecoration: "underline", border: "none", background: "none", cursor: "pointer" }}>
        Retry
      </button>
    </div>
  );

  const SECTION_HEADER = (label: string, count: number, color: string): React.ReactNode => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: "0.06em", color: "#5e6c84" }}>{label}</span>
      <span style={{ ...BADGE, background: color, color: "white" }}>{count}</span>
    </div>
  );

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
          Project Topics
        </h2>
        <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
          Step 2 of 2 — Review how this call relates to the project's topic history.
          Link any missed matches using the "Link to existing" button.
        </p>
      </div>

      {error && (
        <div style={{ background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19" }}>
          {error}
        </div>
      )}

      {/* Followed up */}
      {followed.length > 0 && (
        <div>
          {SECTION_HEADER("Followed Up", followed.length, "#36b37e")}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {followed.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="followed_up"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...followed]; n[i] = u; setFollowed(n); }}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* Not discussed */}
      {notDiscussed.length > 0 && (
        <div>
          {SECTION_HEADER("Not Discussed", notDiscussed.length, "#97a0af")}
          <p style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
            Set a disposition for each topic before validating.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {notDiscussed.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="not_discussed"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...notDiscussed]; n[i] = u; setNotDiscussed(n); }}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* New topics */}
      {newTopics.length > 0 && (
        <div>
          {SECTION_HEADER("New Topics", newTopics.length, "#0052cc")}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {newTopics.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="new_topics"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...newTopics]; n[i] = u; setNewTopics(n); }}
                onLink={(topicId, topicName) => handleLink(i, topicId, topicName)}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* Validate */}
      {!call.is_locked && (
        <div style={{ paddingTop: 8 }}>
          {unacknowledgedCount > 0 && (
            <p style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
              {unacknowledgedCount} not-discussed topic{unacknowledgedCount > 1 ? "s" : ""} need a disposition.
            </p>
          )}
          <button
            onClick={handleValidate}
            disabled={!canValidate}
            style={{
              padding: "10px 24px", borderRadius: 6, border: "none", fontSize: 13, fontWeight: 600,
              background: canValidate ? "#36b37e" : "#f4f5f7",
              color: canValidate ? "white" : "#97a0af",
              cursor: canValidate ? "pointer" : "default",
            }}
          >
            {validating ? "Validating…" : "Validate & Continue →"}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire `ProjectTopicsStage` into `page.tsx`**

Add import:
```typescript
import ProjectTopicsStage from "@/components/ProjectTopicsStage";
```

In the stage routing, add the `project_topics` case:

```tsx
{call.kanban_stage === "project_topics" && (
  <ProjectTopicsStage
    call={call}
    initialResult={aggregateResult}
    onValidated={() => {
      setAggregateResult(null);
      loadCall();
    }}
  />
)}
```

- [ ] **Step 3: Verify TypeScript compiles and ESLint passes**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend
npx tsc --noEmit && npx eslint src/components/ProjectTopicsStage.tsx src/components/CallTopicsStage.tsx
```

Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
cd /Users/louisgarnier/Claude/Project\ management
python3 scripts/git_ops.py commit "[EPIC-7] feat: add ProjectTopicsStage with 3-bucket review and link-to-existing (Story 7.5)" \
  "frontend/src/components/ProjectTopicsStage.tsx" \
  "frontend/app/projects/[id]/calls/[call_id]/page.tsx"
```

---

## Post-build checklist

- [ ] DB migration run in Supabase (011_two_step_topics_stages.sql)
- [ ] All backend tests pass (`python3 -m pytest backend/tests/ -v`)
- [ ] `npx tsc --noEmit` → 0 errors
- [ ] `npx eslint .` → 0 errors
- [ ] Manual: Kanban shows 5 columns (Transcript / Call Topics / Project Topics / Artifacts / Done)
- [ ] Manual: Call 1 → Call Topics → Extract → Continue → auto-advances to Artifacts
- [ ] Manual: Call 2 → Call Topics → Extract → Continue → shows Project Topics 3-bucket
- [ ] Manual: "Link to existing" on new topic → moves card to Followed Up
- [ ] Manual: Artifact generation includes project topic context in output
- [ ] Update `docs/project/config/build-log.md` — add EPIC-7 entry
- [ ] Update `docs/project/config/epics/ACTIVE.md` — advance to EPIC-8
