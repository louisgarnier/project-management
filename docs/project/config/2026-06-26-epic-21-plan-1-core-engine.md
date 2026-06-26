# EPIC-21 Plan #1 — Core Recap Engine (headless) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the headless agentic recap pass — assemble full prior context (recent transcripts + distilled tracker), reconcile the new call's v5 topics into a single versioned project tracker via a self-critiquing LLM pass, and persist it as an unlocked draft.

**Architecture:** A new single-document state model (`project_trackers`, one versioned JSONB per project, mirroring the `tracker_v06.json` lodestar) replaces the scattered downstream tables for the new path. A context-assembly module gathers the v5 extraction output for the current call, the latest tracker, the most-recent-N full transcripts, and per-project glossary. One LLM "recap pass" reconciles (MATCH→VERIFY→APPLY), then a critic pass enforces the honesty rules (no invented items, no dropped topics, grounded status changes) and emits low-confidence flags. The v5 extraction engine is untouched.

**Tech Stack:** Python 3 / FastAPI backend, Supabase (Postgres) via `db.table(...)`, async LLM calls via `backend/services/llm_service.call_llm_raw`, pytest.

## Global Constraints

- **Do NOT modify** `backend/services/call_topics_v5/` — extraction is a black box (spec §4 / decision 1).
- **Never invent** — when unsure, omit + flag, never fabricate (spec decision 9). Applies to every LLM prompt and every validation.
- **No topic silently dropped** — every prior topic is carried forward, explicitly closed, or marked "Not raised" (spec §5.2 drop-out protection).
- **Human-in-the-loop is core** — the pass produces an *unlocked draft*; nothing is auto-locked (spec decision 8). (Locking/editing UI is plan #2 — out of scope here.)
- **Content is per-project, siloed; never read another project's tracker** (spec decision 10).
- **Transcript recency window** default `RECENCY_N = 6` (spec decision 7) — a module constant, tunable.
- All LLM calls use `temperature=0`.
- Logging conventions: `[ModuleName] verb: detail`, emojis 📥📤✅❌⚠️�but for db 🗄️.
- All git via `python3 scripts/git_ops.py` (stages all + commits). Commit format `[EPIC-21] type: desc`.

---

## File Structure

**Create:**
- `backend/database/migrations/040_project_trackers.sql` — versioned tracker table + per-project context column.
- `backend/services/tracker_store.py` — load/save versioned tracker documents.
- `backend/services/tracker_schema.py` — tracker dataclasses/validation + drop-out & invented-item guards.
- `backend/services/recap_context.py` — context assembly for the pass.
- `backend/prompts/recap_pass.py` — methodology system prompt + user-message builder + critic prompt.
- `backend/services/recap_service.py` — orchestrates draft → critique → validate → persist draft.
- `backend/tests/test_tracker_store.py`, `test_tracker_schema.py`, `test_recap_context.py`, `test_recap_service.py`
- `backend/tests/fixtures/tracker_v06.json` — copy of the lodestar (integration oracle).

**Modify:**
- `backend/routers/topics.py` — add `POST /api/calls/{call_id}/recap/run` endpoint (near existing task-grouping endpoints, ~line 617+).

**Untouched:** everything under `backend/services/call_topics_v5/`.

---

### Task 1: Tracker state model + store

> **Before writing the migration, invoke `postgres-best-practices`.** This task creates a new table and a JSONB column.

**Files:**
- Create: `backend/database/migrations/040_project_trackers.sql`
- Create: `backend/services/tracker_store.py`
- Test: `backend/tests/test_tracker_store.py`

**Interfaces:**
- Produces:
  - `load_latest_tracker(project_id: str, db) -> dict | None` — returns the highest-version tracker JSON for a project, or `None` if none exists.
  - `save_tracker_version(project_id: str, tracker: dict, db, locked: bool = False) -> dict` — inserts a new version row (version = prev max + 1), returns the stored row `{id, project_id, version, tracker_json, locked, created_at}`.

- [ ] **Step 1: Write the migration**

```sql
-- 040_project_trackers.sql — EPIC-21: single versioned tracker doc per project
CREATE TABLE IF NOT EXISTS project_trackers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    tracker_json JSONB NOT NULL,
    locked      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, version)
);
CREATE INDEX IF NOT EXISTS idx_project_trackers_latest
    ON project_trackers (project_id, version DESC);

-- Per-project context (glossary/parties/role) lives inside tracker_json.context,
-- but seed an empty context column on projects for the FIRST call when no tracker exists yet.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS recap_context JSONB NOT NULL DEFAULT '{}'::jsonb;
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_tracker_store.py
from backend.services.tracker_store import load_latest_tracker, save_tracker_version
from backend.tests.helpers import FakeDB  # existing test helper; see other service tests for shape

def test_load_returns_none_when_no_tracker():
    db = FakeDB(tables={"project_trackers": []})
    assert load_latest_tracker("proj-1", db) is None

def test_save_increments_version_and_load_returns_latest():
    db = FakeDB(tables={"project_trackers": []})
    save_tracker_version("proj-1", {"topics": []}, db)
    row2 = save_tracker_version("proj-1", {"topics": [{"id": "t1"}]}, db)
    assert row2["version"] == 2
    latest = load_latest_tracker("proj-1", db)
    assert latest == {"topics": [{"id": "t1"}]}
```

> If `FakeDB` does not exist, inspect `backend/tests/test_finalized_topics_service.py` for the established DB-faking pattern and mirror it. Do not invent a new mocking style.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_tracker_store.py -v`
Expected: FAIL (`ModuleNotFoundError: backend.services.tracker_store`)

- [ ] **Step 4: Implement `tracker_store.py`**

```python
"""Versioned single-document tracker store (EPIC-21, ADR-008)."""
import logging
db_logger = logging.getLogger("backend")

def load_latest_tracker(project_id: str, db) -> dict | None:
    res = (db.table("project_trackers")
             .select("tracker_json,version")
             .eq("project_id", project_id)
             .order("version", desc=True)
             .limit(1)
             .execute())
    rows = res.data or []
    if not rows:
        return None
    return rows[0]["tracker_json"]

def save_tracker_version(project_id: str, tracker: dict, db, locked: bool = False) -> dict:
    res = (db.table("project_trackers")
             .select("version")
             .eq("project_id", project_id)
             .order("version", desc=True)
             .limit(1)
             .execute())
    rows = res.data or []
    next_version = (rows[0]["version"] + 1) if rows else 1
    payload = {"project_id": project_id, "version": next_version,
               "tracker_json": tracker, "locked": locked}
    ins = db.table("project_trackers").insert(payload).execute()
    db_logger.info(f"🗄️ [TrackerStore] saved version {next_version} for project {project_id}")
    return ins.data[0]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_tracker_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] feat: project_trackers table + versioned tracker store"
```

---

### Task 2: Tracker schema + drop-out / invented-item guards

**Files:**
- Create: `backend/services/tracker_schema.py`
- Test: `backend/tests/test_tracker_schema.py`
- Reference: `backend/tests/fixtures/tracker_v06.json` (copy from `/Users/louisgarnier/Downloads/files3/tracker_v06.json`)

**Interfaces:**
- Produces:
  - `TOPIC_FIELDS: set[str]` — the canonical per-topic field names.
  - `validate_tracker(tracker: dict) -> list[str]` — returns a list of human-readable schema violations (empty = valid).
  - `assert_no_topic_dropped(prev: dict, new: dict) -> list[str]` — returns ids of prior topics missing from `new` (must be empty; a closed topic stays present with `status="closed"`).

- [ ] **Step 1: Copy the lodestar fixture**

```bash
cp "/Users/louisgarnier/Downloads/files3/tracker_v06.json" "backend/tests/fixtures/tracker_v06.json"
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_tracker_schema.py
import json, pathlib
from backend.services.tracker_schema import validate_tracker, assert_no_topic_dropped

LODESTAR = json.loads((pathlib.Path(__file__).parent / "fixtures/tracker_v06.json").read_text())

def test_lodestar_is_valid():
    assert validate_tracker(LODESTAR) == []

def test_missing_topic_id_is_flagged():
    bad = {"topics": [{"name": "x"}]}  # no id
    violations = validate_tracker(bad)
    assert any("id" in v for v in violations)

def test_dropped_topic_detected():
    prev = {"topics": [{"id": "topic_001"}, {"id": "topic_002"}]}
    new = {"topics": [{"id": "topic_001"}]}
    assert assert_no_topic_dropped(prev, new) == ["topic_002"]

def test_closed_topic_not_treated_as_dropped():
    prev = {"topics": [{"id": "topic_001"}]}
    new = {"topics": [{"id": "topic_001", "status": "closed"}]}
    assert assert_no_topic_dropped(prev, new) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_tracker_schema.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 4: Implement `tracker_schema.py`**

```python
"""Tracker document schema + integrity guards (EPIC-21)."""

TOPIC_FIELDS = {
    "id", "name", "created_in_call", "last_updated_in_call", "status",
    "importance", "is_parked", "key_terms", "current_summary",
    "next_step", "owner", "decisions", "follow_up_items",
    "open_questions", "updates", "rag_grounding_notes",
}
_REQUIRED = {"id", "name", "status"}
_VALID_STATUS = {"open", "closed"}

def validate_tracker(tracker: dict) -> list[str]:
    violations: list[str] = []
    topics = tracker.get("topics")
    if not isinstance(topics, list):
        return ["tracker.topics must be a list"]
    seen_ids = set()
    for i, t in enumerate(topics):
        missing = _REQUIRED - set(t)
        if missing:
            violations.append(f"topic[{i}] missing required field(s): {sorted(missing)}")
        tid = t.get("id")
        if tid in seen_ids:
            violations.append(f"duplicate topic id: {tid}")
        seen_ids.add(tid)
        if "status" in t and t["status"] not in _VALID_STATUS:
            violations.append(f"topic {tid} invalid status: {t['status']}")
    return violations

def assert_no_topic_dropped(prev: dict, new: dict) -> list[str]:
    prev_ids = {t.get("id") for t in prev.get("topics", [])}
    new_ids = {t.get("id") for t in new.get("topics", [])}
    return sorted(prev_ids - new_ids)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_tracker_schema.py -v`
Expected: PASS (4 passed)

> If `test_lodestar_is_valid` fails, the lodestar uses field names this task must absorb — update `TOPIC_FIELDS`/`_REQUIRED` to match the real fixture rather than forcing the fixture to match. The lodestar is the source of truth.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] feat: tracker schema validation + drop-out guard"
```

---

### Task 3: Context assembly

**Files:**
- Create: `backend/services/recap_context.py`
- Test: `backend/tests/test_recap_context.py`

**Interfaces:**
- Consumes: `load_latest_tracker` (Task 1).
- Produces:
  - `RECENCY_N = 6` (module constant).
  - `build_recap_context(call_id: str, db, recency_n: int = RECENCY_N) -> dict` returning:
    ```python
    {
      "project_id": str,
      "new_topics": list[dict],          # current call's v5 synthesized_topics
      "current_transcript": str,
      "current_call_date": str,
      "prior_tracker": dict | None,      # load_latest_tracker(project_id)
      "recent_transcripts": list[{"call_date": str, "transcript": str}],  # most recent N PRIOR calls, full text
      "context": dict,                   # glossary/parties/role from prior_tracker.context or projects.recap_context
    }
    ```

**Implementation notes (read before coding):**
- The current call's extracted topics live in `calls.call_topics_v5_payload["synthesized_topics"]` (Explore map §5). If absent, fall back to `calls.extraction_cache`.
- Fetch all calls for the project ordered by `created_at`; the "recent N prior" set is the N calls with `created_at < current_call.created_at`, newest first. Older calls are intentionally NOT included as raw transcript (spec §5.2 recency window) — they are represented by `prior_tracker`.
- `context` = `prior_tracker["context"]` if a tracker exists, else `projects.recap_context`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_recap_context.py
from backend.services.recap_context import build_recap_context, RECENCY_N
from backend.tests.helpers import FakeDB

def _seed():
    calls = [
        {"id": "c1", "project_id": "p", "created_at": "2026-01-01", "transcript": "T1"},
        {"id": "c2", "project_id": "p", "created_at": "2026-01-08", "transcript": "T2"},
        {"id": "c3", "project_id": "p", "created_at": "2026-01-15", "transcript": "T3",
         "call_topics_v5_payload": {"synthesized_topics": [{"topic_name": "A"}]}},
    ]
    trackers = [{"project_id": "p", "version": 1,
                 "tracker_json": {"topics": [{"id": "t1"}], "context": {"glossary": {"X": "y"}}}}]
    return FakeDB(tables={"calls": calls, "project_trackers": trackers,
                          "projects": [{"id": "p", "recap_context": {}}]})

def test_context_includes_new_topics_and_prior_tracker():
    ctx = build_recap_context("c3", _seed())
    assert ctx["new_topics"] == [{"topic_name": "A"}]
    assert ctx["prior_tracker"]["topics"] == [{"id": "t1"}]
    assert ctx["context"] == {"glossary": {"X": "y"}}

def test_recency_window_excludes_old_transcripts():
    ctx = build_recap_context("c3", _seed(), recency_n=1)
    # only c2 (the single most-recent prior call) included as raw transcript; c1 excluded
    dates = [r["transcript"] for r in ctx["recent_transcripts"]]
    assert dates == ["T2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_recap_context.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Implement `recap_context.py`**

```python
"""Assemble full prior context for the recap pass (EPIC-21, spec §5.2)."""
import logging
from backend.services.tracker_store import load_latest_tracker
db_logger = logging.getLogger("backend")

RECENCY_N = 6

def build_recap_context(call_id: str, db, recency_n: int = RECENCY_N) -> dict:
    call = db.table("calls").select("*").eq("id", call_id).single().execute().data
    project_id = call["project_id"]

    payload = call.get("call_topics_v5_payload") or {}
    new_topics = payload.get("synthesized_topics") or call.get("extraction_cache") or []

    all_calls = (db.table("calls").select("id,created_at,transcript")
                   .eq("project_id", project_id).order("created_at", desc=False)
                   .execute().data or [])
    prior = [c for c in all_calls if c["created_at"] < call["created_at"]]
    recent = list(reversed(prior))[:recency_n]  # newest-first, capped at N
    recent_transcripts = [{"call_date": c["created_at"], "transcript": c.get("transcript") or ""}
                          for c in recent]

    prior_tracker = load_latest_tracker(project_id, db)
    if prior_tracker and prior_tracker.get("context"):
        context = prior_tracker["context"]
    else:
        proj = db.table("projects").select("recap_context").eq("id", project_id).single().execute().data
        context = (proj or {}).get("recap_context") or {}

    db_logger.info(f"📥 [RecapContext] call {call_id}: {len(new_topics)} new topics, "
                   f"{len(recent_transcripts)} recent transcripts, "
                   f"prior_tracker={'yes' if prior_tracker else 'none'}")
    return {
        "project_id": project_id,
        "new_topics": new_topics,
        "current_transcript": call.get("transcript") or "",
        "current_call_date": call["created_at"],
        "prior_tracker": prior_tracker,
        "recent_transcripts": recent_transcripts,
        "context": context,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_recap_context.py -v`
Expected: PASS (2 passed)

> `FakeDB` must support `.single()`. If it doesn't, extend the existing helper minimally (mirror real Supabase `.single().execute().data` returning one dict).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] feat: recap context assembly with transcript recency window"
```

---

### Task 4: Methodology + critic prompts

> **Invoke `api-and-interface-design` before finalizing the user-message contract** — this is the prompt boundary the LLM consumes.

**Files:**
- Create: `backend/prompts/recap_pass.py`
- Test: `backend/tests/test_recap_service.py` (prompt-builder unit tests added here; full pass tested in Task 5)

**Interfaces:**
- Produces:
  - `RECAP_SYSTEM: str` — methodology + honesty rules + output schema (distilled from `New_Project_Tracker_Starter_Prompt.md`).
  - `CRITIC_SYSTEM: str` — checks a draft tracker against the honesty rules; returns issues.
  - `build_recap_user_message(ctx: dict) -> str` — serializes the Task-3 context into the prompt body.
  - `build_critic_user_message(prior: dict | None, draft: dict, transcript: str) -> str`.

- [ ] **Step 1: Write `recap_pass.py`** (no test-first — these are string constants; behavior is exercised in Task 5)

```python
"""Recap pass prompts (EPIC-21). Distilled from New_Project_Tracker_Starter_Prompt.md."""
import json

RECAP_SYSTEM = """You maintain a coherent, drift-resistant project tracker across weekly calls.

You receive: (1) topics already extracted from THIS call, (2) the full prior tracker, \
(3) recent prior call transcripts, (4) a project glossary. Reconcile the new topics into \
the tracker.

METHODOLOGY — for each new topic: MATCH (extend an existing tracker topic, or genuinely new?) \
→ VERIFY (cross-check the match and any status change against the prior transcripts) \
→ APPLY (update the tracker).

TOPIC RULES — a topic needs >=3 of: forward life; an anchor (pending decision / outstanding \
action / open question); specificity (named systems, people, metrics, deadlines); dialogue \
depth (>=2 substantive turns). Future-life-but-no-action items are PARKED (is_parked=true), \
not new topics. Split when sub-items have different owners/timelines/decisions; keep together \
when they feed one decision.

HONESTY RULES (non-negotiable):
- NEVER invent. If a decision/follow-up/owner/status/topic is not grounded in the transcript, \
do NOT include it. When unsure, OMIT and note it in rag_grounding_notes. Omission beats fabrication.
- Surface every match: in rag_grounding_notes say which existing topic you matched and why.
- Flag low-confidence matches/status-changes in rag_grounding_notes (prefix "REVIEW:") rather than guessing.
- If continuation-vs-new is genuinely ambiguous, create it as new and prefix rag_grounding_notes with "ASK:".
- Never auto-close. Mark candidates for closure with rag_grounding_notes "REVIEW: closure?" but keep status open.
- Carry EVERY prior topic forward. If a topic was not discussed this call, keep it and append an \
update {date, summary:"Not raised"}. Never drop a topic.

OUTPUT — return ONLY valid JSON for the full updated tracker, same schema as the input prior \
tracker. Each topic: id, name, created_in_call, last_updated_in_call, status (open/closed), \
importance, is_parked, key_terms, current_summary, next_step, owner, \
decisions:[{text,decided_in}], follow_up_items:[{text,owner,added_in,status,closed_in}], \
open_questions:[{text,added_in,status,resolved_in}], updates:[{date,summary}] (one per call), \
rag_grounding_notes. Preserve existing topic ids. New topics get a new id "topic_NNN"."""

CRITIC_SYSTEM = """You audit a draft project tracker against strict honesty rules. \
Return ONLY JSON: {"issues": [{"topic_id": str, "kind": str, "detail": str}]}. \
kind is one of: invented (item not grounded in transcript), dropped (prior topic missing), \
ungrounded_status (status change with no transcript support), bad_merge (two distinct threads \
merged). If the draft is clean, return {"issues": []}. Do not rewrite the tracker; only report."""

def build_recap_user_message(ctx: dict) -> str:
    parts = [
        f"## Project glossary / context\n{json.dumps(ctx['context'], indent=2)}",
        f"## Prior tracker (full state)\n{json.dumps(ctx['prior_tracker'], indent=2)}",
        "## Recent prior call transcripts (newest first)",
    ]
    for r in ctx["recent_transcripts"]:
        parts.append(f"### Transcript {r['call_date']}\n{r['transcript']}")
    parts.append(f"## THIS call ({ctx['current_call_date']}) — transcript\n{ctx['current_transcript']}")
    parts.append(f"## THIS call — topics already extracted (reconcile these)\n"
                 f"{json.dumps(ctx['new_topics'], indent=2)}")
    return "\n\n".join(parts)

def build_critic_user_message(prior: dict | None, draft: dict, transcript: str) -> str:
    return "\n\n".join([
        f"## Prior tracker\n{json.dumps(prior, indent=2)}",
        f"## Draft updated tracker\n{json.dumps(draft, indent=2)}",
        f"## This call's transcript (ground truth)\n{transcript}",
    ])
```

- [ ] **Step 2: Write a prompt-builder unit test**

```python
# backend/tests/test_recap_service.py  (prompt-builder section)
from backend.prompts.recap_pass import build_recap_user_message

def test_user_message_includes_new_topics_and_prior():
    ctx = {"context": {"glossary": {}}, "prior_tracker": {"topics": [{"id": "t1"}]},
           "recent_transcripts": [{"call_date": "d1", "transcript": "prev"}],
           "current_transcript": "now", "current_call_date": "d2",
           "new_topics": [{"topic_name": "A"}]}
    msg = build_recap_user_message(ctx)
    assert "topic_name" in msg and "Prior tracker" in msg and "prev" in msg and "now" in msg
```

- [ ] **Step 3: Run test to verify it passes**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_recap_service.py::test_user_message_includes_new_topics_and_prior -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] feat: recap methodology + critic prompts"
```

---

### Task 5: Recap service — draft → critique → validate → persist draft

**Files:**
- Create: `backend/services/recap_service.py`
- Modify: `backend/routers/topics.py` (add endpoint)
- Test: `backend/tests/test_recap_service.py` (add orchestration tests with a fake LLM)

**Interfaces:**
- Consumes: `build_recap_context` (T3), `load_latest_tracker`/`save_tracker_version` (T1), `validate_tracker`/`assert_no_topic_dropped` (T2), `RECAP_SYSTEM`/`CRITIC_SYSTEM`/builders (T4), `call_llm_raw` (`backend/services/llm_service.py`).
- Produces:
  - `async run_recap_pass(call_id: str, db, llm: str = "openrouter", model: str | None = None) -> dict`
    returning `{"tracker": dict, "issues": list[dict], "schema_violations": list[str], "dropped": list[str], "version": int}`.
  - The new tracker is persisted via `save_tracker_version(..., locked=False)`.

**Logic (read before coding):**
1. `ctx = build_recap_context(call_id, db)`.
2. If `ctx["prior_tracker"]` is None → this is call 1: build the tracker fresh from `new_topics` (no MATCH/VERIFY). Still run schema validation. (Mirrors the starter prompt's "call 1 = clean extraction only".)
3. Else: call LLM with `RECAP_SYSTEM` + `build_recap_user_message(ctx)`, parse JSON → `draft`.
4. Critic pass: call LLM with `CRITIC_SYSTEM` + `build_critic_user_message(prior, draft, ctx["current_transcript"])` → `issues`.
5. Run `validate_tracker(draft)` and `assert_no_topic_dropped(prior, draft)`.
6. Persist draft via `save_tracker_version`. Return the bundle (issues/violations surfaced to the UI in plan #2).

- [ ] **Step 1: Write failing orchestration tests (fake LLM)**

```python
# backend/tests/test_recap_service.py  (orchestration section)
import json, pytest
from backend.services import recap_service
from backend.tests.helpers import FakeDB

class FakeLLM:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    async def __call__(self, system, user, llm, **kw):
        self.calls.append(system); return self.responses.pop(0)

@pytest.mark.asyncio
async def test_call_1_builds_fresh_tracker(monkeypatch):
    db = FakeDB(tables={
        "calls": [{"id": "c1", "project_id": "p", "created_at": "2026-01-01", "transcript": "T",
                   "call_topics_v5_payload": {"synthesized_topics":
                       [{"topic_name": "A", "tasks": []}]}}],
        "project_trackers": [], "projects": [{"id": "p", "recap_context": {}}]})
    out = await recap_service.run_recap_pass("c1", db)
    assert out["schema_violations"] == []
    assert len(out["tracker"]["topics"]) == 1
    assert out["version"] == 1

@pytest.mark.asyncio
async def test_call_2_reconciles_and_runs_critic(monkeypatch):
    draft = {"topics": [{"id": "topic_001", "name": "A", "status": "open"}], "context": {}}
    fake = FakeLLM([json.dumps(draft), json.dumps({"issues": []})])
    monkeypatch.setattr(recap_service, "call_llm_raw", fake)
    db = FakeDB(tables={
        "calls": [
            {"id": "c1", "project_id": "p", "created_at": "2026-01-01", "transcript": "T1"},
            {"id": "c2", "project_id": "p", "created_at": "2026-01-08", "transcript": "T2",
             "call_topics_v5_payload": {"synthesized_topics": [{"topic_name": "A"}]}}],
        "project_trackers": [{"project_id": "p", "version": 1,
            "tracker_json": {"topics": [{"id": "topic_001", "name": "A", "status": "open"}], "context": {}}}],
        "projects": [{"id": "p", "recap_context": {}}]})
    out = await recap_service.run_recap_pass("c2", db)
    assert len(fake.calls) == 2            # recap + critic
    assert out["dropped"] == []            # topic_001 preserved
    assert out["version"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_recap_service.py -v`
Expected: FAIL (`AttributeError`/`ModuleNotFoundError` on `recap_service.run_recap_pass`)

- [ ] **Step 3: Implement `recap_service.py`**

```python
"""Agentic recap pass orchestration (EPIC-21, spec §5.2)."""
import json, logging
from backend.services.llm_service import call_llm_raw
from backend.services.recap_context import build_recap_context
from backend.services.tracker_store import load_latest_tracker, save_tracker_version
from backend.services.tracker_schema import validate_tracker, assert_no_topic_dropped
from backend.prompts.recap_pass import (
    RECAP_SYSTEM, CRITIC_SYSTEM, build_recap_user_message, build_critic_user_message)

db_logger = logging.getLogger("backend")

def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip() if "```" in raw else raw
    return json.loads(raw)

def _fresh_tracker(project_id: str, ctx: dict) -> dict:
    topics = []
    for i, nt in enumerate(ctx["new_topics"], start=1):
        topics.append({
            "id": f"topic_{i:03d}",
            "name": nt.get("topic_name") or nt.get("name") or "Untitled",
            "created_in_call": ctx["current_call_date"],
            "last_updated_in_call": ctx["current_call_date"],
            "status": "open", "importance": nt.get("importance", "medium"),
            "is_parked": False, "key_terms": nt.get("key_terms", []),
            "current_summary": nt.get("current_summary", ""),
            "next_step": nt.get("next_step", ""), "owner": nt.get("owner", ""),
            "decisions": nt.get("decisions", []), "follow_up_items": [],
            "open_questions": nt.get("open_questions", []),
            "updates": [{"date": ctx["current_call_date"], "summary": nt.get("current_summary", "")}],
            "rag_grounding_notes": "Call 1: clean extraction, no matching.",
        })
    return {"project_id": project_id, "context": ctx["context"], "topics": topics}

async def run_recap_pass(call_id: str, db, llm: str = "openrouter", model: str | None = None) -> dict:
    ctx = build_recap_context(call_id, db)
    prior = ctx["prior_tracker"]
    issues: list[dict] = []

    if prior is None:
        db_logger.info(f"🚀 [Recap] call {call_id}: no prior tracker → fresh build")
        tracker = _fresh_tracker(ctx["project_id"], ctx)
    else:
        raw = await call_llm_raw(RECAP_SYSTEM, build_recap_user_message(ctx), llm,
                                 max_tokens=8192, model=model, temperature=0)
        tracker = _parse_json(raw)
        critic_raw = await call_llm_raw(
            CRITIC_SYSTEM, build_critic_user_message(prior, tracker, ctx["current_transcript"]),
            llm, max_tokens=4096, model=model, temperature=0)
        issues = _parse_json(critic_raw).get("issues", [])

    violations = validate_tracker(tracker)
    dropped = assert_no_topic_dropped(prior, tracker) if prior else []
    row = save_tracker_version(ctx["project_id"], tracker, db, locked=False)
    db_logger.info(f"✅ [Recap] call {call_id}: v{row['version']} saved — "
                   f"{len(issues)} issues, {len(violations)} schema violations, {len(dropped)} dropped")
    return {"tracker": tracker, "issues": issues, "schema_violations": violations,
            "dropped": dropped, "version": row["version"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/test_recap_service.py -v`
Expected: PASS (3 passed incl. the Task-4 prompt test)

- [ ] **Step 5: Add the router endpoint**

In `backend/routers/topics.py`, near the task-grouping endpoints (~line 617), add:

```python
from backend.services.recap_service import run_recap_pass  # top of file with other imports

@router.post("/calls/{call_id}/recap/run")
async def run_recap_endpoint(call_id: str):
    db = get_db()
    db_logger.info(f"📥 [API] recap run requested: {call_id}")
    result = await run_recap_pass(call_id, db)
    return result
```

> Match the existing endpoint style in this file (how `db` is obtained, how async handlers are declared). Mirror, don't invent.

- [ ] **Step 6: Run full backend suite to confirm no regressions**

Run: `cd "/Users/louisgarnier/Claude/Project management" && python3 -m pytest backend/tests/ -q`
Expected: all prior tests still pass + the new ones.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] feat: agentic recap pass (draft+critic+validate) + /recap/run endpoint"
```

---

### Task 6: Integration test against the lodestar

**Files:**
- Test: `backend/tests/test_recap_lodestar.py`
- Uses: `backend/tests/fixtures/tracker_v06.json` (Task 2)

**Goal:** This is the real test oracle (spec §7). It is a *manual/opt-in* integration test (hits a live LLM), gated behind an env flag so CI stays deterministic. It verifies the acceptance bar: no topic dropped, no invented items, schema valid.

- [ ] **Step 1: Write the gated integration test**

```python
# backend/tests/test_recap_lodestar.py
import os, json, pathlib, pytest
from backend.services.tracker_schema import validate_tracker, assert_no_topic_dropped

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LODESTAR") != "1", reason="set RUN_LODESTAR=1 to run live-LLM lodestar test")

LODESTAR = json.loads((pathlib.Path(__file__).parent / "fixtures/tracker_v06.json").read_text())

@pytest.mark.asyncio
async def test_recap_holds_against_lodestar_call(tmp_path):
    # Feed the prior tracker = lodestar truncated to call N-1, plus call N's transcript+topics.
    # Assert: schema valid, zero dropped topics, zero critic 'invented' issues.
    # (Wire to a real project/call seeded from the SWIB fixture set — see runbook.)
    ...
```

> The body wires to a seeded SWIB project once plan #4's migration backfills lodestar data, OR runs against `/Users/louisgarnier/Downloads/files3/` inputs directly. Until then, this test documents the bar and stays skipped. Do NOT delete it — it is the acceptance oracle.

- [ ] **Step 2: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-21] test: lodestar integration oracle (gated, skipped by default)"
```

---

## Self-Review

**Spec coverage:**
- §5.1 keep v5 → Global Constraints (untouched). ✓
- §5.2 full prior context + recency window → Task 3. ✓
- §5.2 reconcile-not-rebuild (map v5 fields) → Task 4 prompt + Task 5 `_fresh_tracker`. ✓
- §5.2 self-critique → Task 5 critic pass. ✓
- §5.2 never-invent / abstain → Task 4 RECAP_SYSTEM honesty rules + Task 5 critic. ✓
- §5.2 drop-out protection → Task 2 `assert_no_topic_dropped` + Task 5. ✓
- §5.3 persistence/versioning → Task 1 store. ✓
- §6 data shape → Task 2 schema. ✓
- §7 test bar → Task 6 lodestar oracle. ✓
- Decision 8 (human-in-loop / unlocked draft) → Task 5 saves `locked=False`. ✓
- Decision 10 (per-project siloing) → store always scoped by `project_id`. ✓

**Deferred to later plans (not this plan):** editable-output UI + Validate button (plan #2), Excel render (plan #3), teardown/migration of EPIC-19/20 stages + lodestar backfill (plan #4). Kanban-stage renaming and flag-UI presentation belong to plan #2.

**Placeholder scan:** Task 6's test body is intentionally a documented stub (gated, requires live LLM + seeded data from plan #4); flagged as such, not silent. No other placeholders.

**Type consistency:** `build_recap_context` return keys consumed verbatim by `build_recap_user_message` and `run_recap_pass`. `save_tracker_version` return `{version,...}` consumed in Task 5. `assert_no_topic_dropped(prev,new)` signature consistent across Tasks 2 and 5.

## Open decisions folded with defaults (override anytime)
- State model = single versioned `project_trackers` JSONB (ADR-008). 
- Methodology lives as a Python prompt constant (`recap_pass.py`), not an `artifact_library` row — simplest for v1; migrate to library later if per-project editing is wanted.
- `RECENCY_N = 6`.
- LLM defaults to `openrouter` via existing resolver; can switch to the project's configured model.
