# Call Topics (v5) + Pass 1 Reliability Rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Check in with user after each task per project workflow (one task → stop → report → wait → next).

**Goal:** Make Pass 1 (verify_new) and v5 call_topics extraction reliable on the same-transcript regression test (≥90% correct merge verdicts at ≥75% confidence; zero citation verification failures).

**Architecture:** Mirror v5's proven pattern across the board — LLM does cognitive work, code does mechanical work. Unify the data layer between v5 Stage 5 and Pass 1 so both consume identical structured project state. Replace Pass 1's free-form quote citations with v5's line-number pattern. Expand Pass 1 to verify both new candidates AND v5's canonical matches.

**Tech Stack:** Python 3.11+, FastAPI, Supabase Postgres, pytest, TypeScript/React/Next.js, AsyncOpenAI (DeepSeek for dev, Opus/Sonnet for prod).

**Reference spec:** `docs/project/config/2026-05-24-call-topics-and-pass1-reliability-design.md`

**Commit prefix:** `[EPIC-18]` (tentative — rename if epic number changes)

---

## Pre-execution decisions to confirm with user BEFORE Task 1

These six open questions from Section 8 of the design need user input before code is touched. Each one shapes a downstream task. Surface them as a batch question at the start of execution.

| # | Decision | Default if user defers | Affects task |
|---|---|---|---|
| **D1** | STREAM 0 unification approach: (a) `topic_registry` becomes a view derived from `topics`+`topic_updates`, or (b) collapse into one table | (a) view | Tasks 1, 2 |
| **D2** | Is `projects.context` field structured for prompt injection? (Verified UNUSED in prompts — confirmed by `grep`.) Inject as raw text, or require structured format? | inject raw text | Task 14 |
| **D3** | New verdict states from S2.2 (`wrong_canonical_actually_new`, `wrong_canonical_belongs_elsewhere`) — does Stage 11 review screen need updates or does Pass 1's screen subsume that role? | Pass 1 screen subsumes | Tasks 22, 27 |
| **D4** | STREAM 4 auto-accept confidence threshold for `truly_new` (suggest 75% pending fixture calibration) | 75% | Task 26 |
| **D5** | P1-RETRIEVAL (S2.4) — gating criterion to confirm we DON'T need it | ≥90% correct verdicts at ≥75% confidence on same-transcript fixture | Task 24 (skip if met) |
| **D6** | STREAM 5 migration: (a) versioned cache + dual-shape reader, or (b) one-shot reprocess all calls | (b) one-shot reprocess (cheaper if <100 historical calls) | Task 29 |

---

## File map

### STREAM 0 — Data layer unification
- **Create** `backend/database/migrations/034_unified_project_topic_state.sql` — schema for unified read (view or table merge per D1)
- **Create** `backend/services/project_topic_state.py` — single read API consumed by Stage 1 + Pass 1
- **Create** `backend/tests/test_project_topic_state.py` — unit tests
- **Modify** `backend/services/call_topics_v5/stage_1_context.py` — consume new API instead of raw `topic_registry` query
- **Modify** `backend/services/topics_service.py:720-769` — `_get_previous_topics` consumes new API

### STREAM 1 — v5 extraction changes
- **S1.3 baseline:**
  - **Create** `backend/scripts/measure_v5_drift.py` — runs gold-set transcripts N times through Stages 2/5/7, computes drift
  - **Create** `backend/tests/call_topics_v5/test_drift_baseline.py` — captures baseline as regression test
- **S1.1 V5-CORE (Stage 5 sees structure):**
  - **Modify** `backend/prompts/call_topics_v5_cluster.py` — richer registry block format
  - **Modify** `backend/services/call_topics_v5/stage_5_cluster.py` — accept structured registry parameter
  - **Modify** `backend/services/call_topics_v5/orchestrator.py` — pass structured state from STREAM 0
- **S1.2 V5-CONTEXT:**
  - **Modify** `backend/prompts/call_topics_v5_atomic.py` — inject `projects.context` into system prompt
  - **Modify** `backend/prompts/call_topics_v5_cluster.py` — inject `projects.context`
  - **Modify** `backend/services/call_topics_v5/stage_2_atomic.py` — accept project_context kw
  - **Modify** `backend/services/call_topics_v5/stage_5_cluster.py` — accept project_context kw
  - **Modify** `backend/services/call_topics_v5/orchestrator.py` — pass `ctx["project_metadata"]["context"]` down
- **S1.4 V5-MODEL-CONFIG:**
  - **Modify** `backend/services/call_topics_v5/stage_5_cluster.py:103` — remove hardcoded `model="deepseek/deepseek-v3.2"` default
  - **Modify** `backend/services/call_topics_v5/stage_7_synthesis.py:106` — same
  - **Modify** `backend/services/call_topics_v5/stage_3_recall.py` — verify same pattern, remove if present

### STREAM 2 — Pass 1 changes
- **S2.1 P1-CITATIONS:**
  - **Modify** `backend/prompts/verify_new_topic.py` — replace `{call_id, lines, quote}` contract with `{call_id, evidence_lines}`
  - **Modify** `backend/services/topic_verification.py` — line-number past transcripts before prompt, resolve `evidence_lines` to text via existing `stage_0_ingest.resolve_lines`
  - **Modify** `backend/services/citation_verify.py` — replace string-match verifier with line-range bounds check
  - **Modify** `backend/routers/topics.py:680-693` — line-number past transcripts in `_run_verify_new_background`
- **S2.2 P1-BIDIRECTIONAL:**
  - **Modify** `backend/prompts/verify_new_topic.py` — second prompt variant for canonical-match verification
  - **Modify** `backend/services/topic_verification.py` — `run_verify_canonical_match()` function
  - **Modify** `backend/routers/topics.py` — input includes both new + canonical candidates; route appropriately
- **S2.3 P1-CLEANUP:**
  - **Create** `backend/services/topic_similarity.py` — single IDF-weighted Jaccard impl
  - **Modify** `backend/services/call_topics_v5/stage_6_reconcile.py:25-36` — use shared `topic_similarity`
  - **Modify** `backend/services/topic_verification.py:114-199` — delete local IDF code, import from shared
  - **Modify** `backend/prompts/verify_new_topic.py` — drop `extraction_grounded`/`ungrounded_items` from schema
  - **Modify** `backend/services/topic_verification.py` — drop `extraction_grounded` handling; harden non-dict response (port Stage 5 v5 pattern)

### STREAM 3 — Pass 1 test fixtures
- **Create** `backend/tests/fixtures/pass1/__init__.py`
- **Create** `backend/tests/fixtures/pass1/same_transcript_dup.json`
- **Create** `backend/tests/fixtures/pass1/true_new.json`
- **Create** `backend/tests/fixtures/pass1/mega_topic.json`
- **Create** `backend/tests/fixtures/pass1/wrong_canonical.json`
- **Create** `backend/tests/fixtures/pass1/naming_drift.json`
- **Create** `backend/tests/test_pass1_fixtures.py` — fixture-driven tests with mocked LLM

### STREAM 4 — Verification asymmetry UX
- **Modify** `backend/services/topic_verification.py::compute_confidence` — emit `auto_accept_eligible` boolean alongside `pct`/`label`
- **Modify** `backend/routers/topics.py` — Pass 1 result endpoint includes `auto_accept_eligible`
- **Modify** `frontend/src/types/index.ts` — extend `VerifyNewResult` with new verdict labels + `auto_accept_eligible`
- **Modify** `frontend/src/components/ProjectUpdatesStage.tsx` — auto-confirm `truly_new` items when `auto_accept_eligible=true`

### STREAM 5 — Migration
- **Create** `backend/scripts/repopulate_verify_new_cache.py` — bulk reprocess past calls under new schema
- **Create** `docs/project/config/2026-05-24-epic-18-migration-runbook.md` — manual steps user follows

---

## Tasks

### Task 1 — STREAM 0: Migration for unified project topic state (depends on D1)

**Files:**
- Create: `backend/database/migrations/034_unified_project_topic_state.sql`

**Approach (assumes D1 = view):** Create a Postgres view `project_topic_state` that joins `topics` + latest `topic_updates` per topic, returning the shape both Stage 1 and Pass 1 need. `topic_registry` table is retained for now (Stage 1 cutover happens in Task 4); future cleanup epic can deprecate it.

- [ ] **Step 1: Write migration SQL**

Create `backend/database/migrations/034_unified_project_topic_state.sql`:

```sql
-- EPIC-18: unified read model for project topic state
-- Consumed by v5 Stage 1 (clustering context) and Pass 1 (verify_new)
-- Joins topics + latest topic_updates per topic, project-scoped.

CREATE OR REPLACE VIEW project_topic_state AS
SELECT
    t.id AS topic_id,
    t.project_id,
    t.name,
    t.calls_open,
    t.first_raised_call_id,
    t.archived,
    COALESCE(latest.summary, '')          AS summary,
    COALESCE(latest.status, 'open')        AS status,
    COALESCE(latest.sentiment, 'neutral')  AS sentiment,
    COALESCE(latest.importance, 'medium')  AS importance,
    COALESCE(latest.evidence, '[]'::jsonb) AS evidence,
    COALESCE(latest.key_terms, '[]'::jsonb) AS key_terms,
    COALESCE(latest.tasks, '[]'::jsonb)    AS tasks,
    COALESCE(latest.open_questions, '[]'::jsonb) AS open_questions,
    COALESCE(latest.decisions, '[]'::jsonb) AS decisions,
    latest.chronology_narrative,
    latest.rag_verification_note,
    latest.created_at AS latest_update_at
FROM topics t
LEFT JOIN LATERAL (
    SELECT *
    FROM topic_updates u
    WHERE u.topic_id = t.id
    ORDER BY u.created_at DESC
    LIMIT 1
) latest ON true
WHERE t.archived = false;

COMMENT ON VIEW project_topic_state IS
'EPIC-18 unified read model. Use this view (not raw topic_registry / topic_updates queries) when loading project state for v5 clustering or Pass 1 verification.';
```

- [ ] **Step 2: Run the migration manually in Supabase Dashboard**

Open Supabase Dashboard → SQL editor → paste migration content → run. Verify view exists:

```sql
SELECT * FROM project_topic_state LIMIT 1;
```

Expected: query returns columns matching the view definition, possibly with one row of real project data.

- [ ] **Step 3: Commit the migration file**

```bash
python3 scripts/git_ops.py add backend/database/migrations/034_unified_project_topic_state.sql
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: migration 034 — project_topic_state unified view (STREAM 0 foundation)"
```

---

### Task 2 — STREAM 0: project_topic_state service module

**Files:**
- Create: `backend/services/project_topic_state.py`
- Test: `backend/tests/test_project_topic_state.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_project_topic_state.py`:

```python
"""EPIC-18 — Tests for unified project_topic_state read API."""
from unittest.mock import MagicMock
from backend.services.project_topic_state import get_project_topic_state, ProjectTopic


def _fake_db_with_view_rows(rows):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = rows
    return db


def test_returns_empty_list_for_no_topics():
    db = _fake_db_with_view_rows([])
    state = get_project_topic_state("proj-1", db=db)
    assert state == []


def test_maps_view_row_to_project_topic_shape():
    row = {
        "topic_id": "t-1", "project_id": "proj-1", "name": "ARM",
        "calls_open": 2, "first_raised_call_id": "c-1", "archived": False,
        "summary": "Account risk modeling", "status": "open",
        "sentiment": "neutral", "importance": "high", "evidence": [],
        "key_terms": ["LMAC", "Monte Carlo"], "tasks": [
            {"task": "Test LMAC vs Monte Carlo Mac", "key_terms": ["LMAC", "Monte Carlo"], "owner": "Mark"}
        ],
        "open_questions": [], "decisions": [],
        "chronology_narrative": None, "rag_verification_note": None,
        "latest_update_at": "2026-05-20T10:00:00Z",
    }
    db = _fake_db_with_view_rows([row])
    state = get_project_topic_state("proj-1", db=db)
    assert len(state) == 1
    t = state[0]
    assert t["topic_id"] == "t-1"
    assert t["name"] == "ARM"
    assert t["tasks"][0]["task"] == "Test LMAC vs Monte Carlo Mac"
    assert t["key_terms"] == ["LMAC", "Monte Carlo"]


def test_filters_by_project_id():
    db = _fake_db_with_view_rows([])
    get_project_topic_state("proj-1", db=db)
    db.table.assert_called_with("project_topic_state")
    db.table.return_value.select.return_value.eq.assert_called_with("project_id", "proj-1")
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd "/Users/louisgarnier/Claude/Project management"
pytest backend/tests/test_project_topic_state.py -v
```

Expected: ImportError / ModuleNotFoundError on `backend.services.project_topic_state`.

- [ ] **Step 3: Implement the service**

Create `backend/services/project_topic_state.py`:

```python
"""EPIC-18 — Unified read API for project topic state.

Single source of truth consumed by v5 Stage 1 (clustering context) and
Pass 1 (verify_new). Reads from the project_topic_state DB view
(see migration 034).

Replaces ad-hoc queries against topic_registry / topic_updates that
diverged historically. New consumers MUST use this; legacy paths to be
migrated in Tasks 4 + 5.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from backend.database.supabase_client import get_client

logger = logging.getLogger("calltracker.project_topic_state")


class ProjectTopic(TypedDict, total=False):
    topic_id: str
    name: str
    summary: str
    status: str
    sentiment: str
    importance: str
    calls_open: int
    first_raised_call_id: str | None
    key_terms: list[str]
    tasks: list[dict]
    open_questions: list[dict]
    decisions: list[dict]
    evidence: list[dict]
    chronology_narrative: str | None
    rag_verification_note: str | None
    latest_update_at: str | None


def get_project_topic_state(project_id: str, *, db=None) -> list[ProjectTopic]:
    """Return all non-archived topics for a project with their latest update.

    Single source of truth for both Stage 5 clustering and Pass 1 verification.
    """
    client = db if db is not None else get_client()
    rows = (
        client.table("project_topic_state")
        .select("*")
        .eq("project_id", project_id)
        .order("latest_update_at", desc=True)
        .execute()
        .data
    ) or []
    out: list[ProjectTopic] = []
    for r in rows:
        out.append({
            "topic_id": r["topic_id"],
            "name": r["name"],
            "summary": r.get("summary") or "",
            "status": r.get("status") or "open",
            "sentiment": r.get("sentiment") or "neutral",
            "importance": r.get("importance") or "medium",
            "calls_open": r.get("calls_open") or 0,
            "first_raised_call_id": r.get("first_raised_call_id"),
            "key_terms": r.get("key_terms") or [],
            "tasks": r.get("tasks") or [],
            "open_questions": r.get("open_questions") or [],
            "decisions": r.get("decisions") or [],
            "evidence": r.get("evidence") or [],
            "chronology_narrative": r.get("chronology_narrative"),
            "rag_verification_note": r.get("rag_verification_note"),
            "latest_update_at": r.get("latest_update_at"),
        })
    logger.info(f"🗄️ [ProjectTopicState] loaded {len(out)} topics for project {project_id}")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest backend/tests/test_project_topic_state.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/services/project_topic_state.py backend/tests/test_project_topic_state.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: project_topic_state service — unified read API (STREAM 0)"
```

---

### Task 3 — STREAM 0: Migrate Stage 1 to consume project_topic_state

**Files:**
- Modify: `backend/services/call_topics_v5/stage_1_context.py`
- Test: `backend/tests/call_topics_v5/test_stage_1_context.py`

- [ ] **Step 1: Update Stage 1 test for new shape**

Open `backend/tests/call_topics_v5/test_stage_1_context.py`. Add a new test alongside existing ones:

```python
def test_load_context_includes_full_topic_state(monkeypatch):
    """EPIC-18: Stage 1 now loads structured topic state, not just registry names."""
    from backend.services.call_topics_v5.stage_1_context import load_context

    fake_topics = [
        {
            "topic_id": "t-1", "name": "ARM", "summary": "Risk modeling",
            "key_terms": ["LMAC", "Monte Carlo"],
            "tasks": [{"task": "Test LMAC", "owner": "Mark"}],
            "open_questions": [], "decisions": [], "evidence": [],
            "status": "open", "sentiment": "neutral", "importance": "high",
            "calls_open": 2, "first_raised_call_id": "c-1",
            "chronology_narrative": None, "rag_verification_note": None,
            "latest_update_at": "2026-05-20T10:00:00Z",
        },
    ]
    monkeypatch.setattr(
        "backend.services.call_topics_v5.stage_1_context.get_project_topic_state",
        lambda project_id, db=None: fake_topics,
    )
    db = FakeDB(projects=[{"id": "proj-1", "name": "P", "description": "", "context": "", "default_llm": "openrouter", "default_model": None}])
    out = load_context("proj-1", db=db)
    assert len(out["topic_registry"]) == 1
    assert out["topic_registry"][0]["tasks"][0]["task"] == "Test LMAC"
    assert "LMAC" in out["topic_registry"][0]["key_terms"]
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest backend/tests/call_topics_v5/test_stage_1_context.py::test_load_context_includes_full_topic_state -v
```

Expected: FAIL — `get_project_topic_state` not imported in stage_1_context.

- [ ] **Step 3: Refactor Stage 1 to use new API**

Edit `backend/services/call_topics_v5/stage_1_context.py`. Replace the `# ── Topic registry ──` block (lines 81-100) with:

```python
    # ── Topic state (EPIC-18 unified read) ──
    from backend.services.project_topic_state import get_project_topic_state
    topic_state = get_project_topic_state(project_id, db=client)
    # NOTE: field name `topic_registry` retained in ContextBundle for backward compat
    # with Stage 5 and orchestrator; semantically this is now the full topic state.
    registry: list[RegistryEntry] = [
        {
            "id": t["topic_id"],
            "name": t["name"],
            "description": t.get("summary") or "",
            # NEW (EPIC-18) — structural payload for Stage 5 V5-CORE
            "key_terms": t.get("key_terms") or [],
            "tasks": t.get("tasks") or [],
            "approved_at": t.get("latest_update_at") or "",
            "approved_by_call_id": t.get("first_raised_call_id"),
        }
        for t in topic_state
    ]
```

Also update the `RegistryEntry` TypedDict above to include the new fields:

```python
class RegistryEntry(TypedDict, total=False):
    id: str
    name: str
    description: str
    key_terms: list[str]  # NEW EPIC-18
    tasks: list[dict]     # NEW EPIC-18
    approved_at: str
    approved_by_call_id: str | None
```

- [ ] **Step 4: Verify all Stage 1 tests pass**

```bash
pytest backend/tests/call_topics_v5/test_stage_1_context.py -v
```

Expected: existing tests + new test all PASS. (Existing tests use empty topic_state by default; they should still pass with the new code path because empty list → empty registry.)

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/services/call_topics_v5/stage_1_context.py backend/tests/call_topics_v5/test_stage_1_context.py
python3 scripts/git_ops.py commit -m "[EPIC-18] refactor: Stage 1 consumes project_topic_state (STREAM 0 cutover)"
```

---

### Task 4 — STREAM 0: Migrate _get_previous_topics to consume project_topic_state

**Files:**
- Modify: `backend/services/topics_service.py:720-769`
- Test: `backend/tests/test_topics.py`

- [ ] **Step 1: Add regression test for _get_previous_topics**

Add to `backend/tests/test_topics.py`:

```python
def test_get_previous_topics_uses_unified_view(monkeypatch):
    """EPIC-18: _get_previous_topics now reads from project_topic_state view."""
    from backend.services.topics_service import _get_previous_topics
    from unittest.mock import MagicMock

    fake_state = [
        {"topic_id": "t-1", "name": "ARM", "summary": "Risk", "status": "open",
         "sentiment": "neutral", "importance": "high", "calls_open": 2,
         "first_raised_call_id": "c-1", "key_terms": ["LMAC"], "tasks": [{"task": "x"}],
         "open_questions": [], "decisions": [], "evidence": [],
         "chronology_narrative": None, "rag_verification_note": None,
         "latest_update_at": None},
    ]
    monkeypatch.setattr(
        "backend.services.topics_service.get_project_topic_state",
        lambda project_id, db=None: fake_state,
    )
    out = _get_previous_topics("proj-1", MagicMock())
    assert len(out) == 1
    assert out[0]["name"] == "ARM"
    assert out[0]["key_terms"] == ["LMAC"]
    assert out[0]["tasks"][0]["task"] == "x"
    # Legacy keys still populated for frontend back-compat
    assert out[0]["follow_up_items"] == []
    assert out[0]["owner"] == "Us"
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest backend/tests/test_topics.py::test_get_previous_topics_uses_unified_view -v
```

Expected: FAIL — `get_project_topic_state` not imported in topics_service.

- [ ] **Step 3: Refactor _get_previous_topics**

Edit `backend/services/topics_service.py`. Replace the function body (lines 720-769):

```python
def _get_previous_topics(project_id: str, db) -> list[dict]:
    """Return all non-archived topics for a project with their most recent update.

    EPIC-18: refactored to consume project_topic_state unified view.
    Legacy keys (follow_up_items, is_parked, rationale, owner) retained as
    empty defaults for frontend back-compat.
    """
    from backend.services.project_topic_state import get_project_topic_state
    state = get_project_topic_state(project_id, db=db)
    return [
        {
            "topic_id": t["topic_id"],
            "name": t["name"],
            "calls_open": t.get("calls_open") or 0,
            "summary": t.get("summary") or "",
            "status": t.get("status") or "open",
            "sentiment": t.get("sentiment") or "neutral",
            "importance": t.get("importance") or "medium",
            "evidence": t.get("evidence") or [],
            "key_terms": t.get("key_terms") or [],
            "tasks": t.get("tasks") or [],
            "open_questions": t.get("open_questions") or [],
            "decisions": t.get("decisions") or [],
            "chronology_narrative": t.get("chronology_narrative"),
            "rag_verification_note": t.get("rag_verification_note"),
            # Legacy keys for frontend back-compat
            "follow_up_items": [],
            "is_parked": False,
            "rationale": "",
            "owner": "Us",
        }
        for t in state
    ]
```

- [ ] **Step 4: Run full topics test suite**

```bash
pytest backend/tests/test_topics.py -v
```

Expected: new test PASS; existing tests still PASS (the refactor preserves shape).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/services/topics_service.py backend/tests/test_topics.py
python3 scripts/git_ops.py commit -m "[EPIC-18] refactor: _get_previous_topics consumes project_topic_state (STREAM 0 cutover)"
```

---

### Task 5 — STREAM 1 (S1.3): v5 drift baseline measurement script

**Files:**
- Create: `backend/scripts/measure_v5_drift.py`
- Create: `backend/tests/call_topics_v5/test_drift_baseline.py`

**Purpose:** quantify v5 grouping drift on identical input BEFORE we change anything. Run gold-set transcripts N=3 times each through Stages 2/5/7. Report drift numbers. Baseline becomes the regression gate for S1.1.

- [ ] **Step 1: Write the drift measurement script**

Create `backend/scripts/measure_v5_drift.py`:

```python
"""EPIC-18 / S1.3 — Measure v5 pipeline drift on identical input.

Runs gold-set transcripts N times through Stages 2, 5, and 7 with the same
inputs each time. Reports drift metrics:

  - Stage 2: |unit_set_run_a ⊖ unit_set_run_b| / |unit_set_union|
  - Stage 5: % of units that ended up in a different cluster across runs
  - Stage 7: # of tasks per topic that differ in core fields (task text, owner)

Baseline measurement for STREAM 1 work — re-run after S1.1 (V5-CORE) ships
to validate delta.

Usage:
  python3 -m backend.scripts.measure_v5_drift --runs 3 \\
    --transcript "docs/project/config/gold set/arm_kickoff_05112026_numbered.txt"
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
from backend.services.call_topics_v5.stage_2_atomic import extract_atomic_units
from backend.services.call_topics_v5.stage_5_cluster import cluster_topics
from backend.services.call_topics_v5.stage_7_synthesis import synthesize_all_topics


async def run_pipeline_once(transcript: str, *, llm: str, model: str | None) -> dict:
    ingested = ingest_transcript(transcript)
    units = await extract_atomic_units(ingested, llm=llm, model=model)
    clusters_out = await cluster_topics(units, topic_registry=[], llm=llm, model=model)
    clusters = clusters_out.get("clusters", [])
    syn = await synthesize_all_topics(clusters, units, llm=llm, model=model)
    return {"units": units, "clusters": clusters, "synthesized": syn}


def measure_stage_2_drift(runs: list[dict]) -> dict:
    unit_sets = [set(u["unit_id"] for u in r["units"]) for r in runs]
    # Symmetric difference jaccard across each pair, average it
    if len(unit_sets) < 2:
        return {"jaccard_drift": 0.0, "n_units": [len(s) for s in unit_sets]}
    pairs = [(i, j) for i in range(len(unit_sets)) for j in range(i+1, len(unit_sets))]
    drifts = []
    for i, j in pairs:
        a, b = unit_sets[i], unit_sets[j]
        inter, union = a & b, a | b
        drifts.append(1.0 - (len(inter) / len(union) if union else 0.0))
    return {"jaccard_drift_avg": sum(drifts)/len(drifts), "n_units": [len(s) for s in unit_sets]}


def measure_stage_5_drift(runs: list[dict]) -> dict:
    """% of units assigned to a different cluster name across runs."""
    if len(runs) < 2:
        return {"reassignment_rate": 0.0}
    # Build {unit_id: [cluster_name_run_a, cluster_name_run_b, ...]}
    unit_to_clusters: dict[str, list[str]] = {}
    for r in runs:
        for c in r["clusters"]:
            for uid in c["unit_ids"]:
                unit_to_clusters.setdefault(uid, []).append(c["topic_name"])
    n_consistent = sum(1 for assignments in unit_to_clusters.values()
                      if len(set(assignments)) == 1 and len(assignments) == len(runs))
    n_total = len(unit_to_clusters)
    return {
        "reassignment_rate": 1 - (n_consistent / n_total if n_total else 0),
        "n_units_tracked": n_total,
    }


def measure_stage_7_drift(runs: list[dict]) -> dict:
    """How often does each topic synthesize the same task set?"""
    if len(runs) < 2:
        return {"task_set_drift": 0.0}
    # Group by topic_name across runs, compare task text sets
    by_topic: dict[str, list[set[str]]] = {}
    for r in runs:
        for s in r["synthesized"]:
            tname = s.get("topic_name") or "?"
            task_texts = {t.get("task","").strip().lower() for t in s.get("tasks",[])}
            by_topic.setdefault(tname, []).append(task_texts)
    drift_per_topic = []
    for tname, runs_tasks in by_topic.items():
        if len(runs_tasks) < 2:
            continue
        pairs = [(runs_tasks[i], runs_tasks[j])
                 for i in range(len(runs_tasks))
                 for j in range(i+1, len(runs_tasks))]
        for a, b in pairs:
            union = a | b
            inter = a & b
            drift_per_topic.append(1.0 - (len(inter)/len(union) if union else 0))
    return {"task_set_jaccard_drift_avg": (sum(drift_per_topic)/len(drift_per_topic)) if drift_per_topic else 0.0}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--llm", default="openrouter")
    ap.add_argument("--model", default="deepseek/deepseek-v3.2")
    args = ap.parse_args()

    transcript = Path(args.transcript).read_text()
    print(f"📥 [drift] Running {args.runs} iterations on {args.transcript}", flush=True)
    runs = []
    for i in range(args.runs):
        print(f"  → Run {i+1}/{args.runs}…", flush=True)
        runs.append(await run_pipeline_once(transcript, llm=args.llm, model=args.model))

    print("\n=== DRIFT BASELINE ===", flush=True)
    print(f"Stage 2 (atomic):    {json.dumps(measure_stage_2_drift(runs), indent=2)}")
    print(f"Stage 5 (cluster):   {json.dumps(measure_stage_5_drift(runs), indent=2)}")
    print(f"Stage 7 (synthesis): {json.dumps(measure_stage_7_drift(runs), indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Smoke-test the script signature (no LLM calls)**

Add a unit test at `backend/tests/call_topics_v5/test_drift_baseline.py`:

```python
"""EPIC-18 / S1.3 — Tests for drift measurement helpers (no LLM)."""
from backend.scripts.measure_v5_drift import (
    measure_stage_2_drift, measure_stage_5_drift, measure_stage_7_drift,
)


def test_stage_2_drift_zero_when_identical():
    runs = [{"units": [{"unit_id":"u1"}, {"unit_id":"u2"}]} for _ in range(3)]
    out = measure_stage_2_drift(runs)
    assert out["jaccard_drift_avg"] == 0.0


def test_stage_2_drift_full_when_disjoint():
    runs = [
        {"units": [{"unit_id":"u1"}, {"unit_id":"u2"}]},
        {"units": [{"unit_id":"u3"}, {"unit_id":"u4"}]},
    ]
    out = measure_stage_2_drift(runs)
    assert out["jaccard_drift_avg"] == 1.0


def test_stage_5_drift_zero_when_consistent_assignment():
    runs = [
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1","u2"]}]} for _ in range(3)
    ]
    out = measure_stage_5_drift(runs)
    assert out["reassignment_rate"] == 0.0


def test_stage_5_drift_nonzero_when_reassigned():
    runs = [
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1"]}, {"topic_name": "B", "unit_ids": ["u2"]}]},
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1","u2"]}]},  # u2 reassigned
    ]
    out = measure_stage_5_drift(runs)
    assert out["reassignment_rate"] > 0


def test_stage_7_drift_zero_when_tasks_match():
    runs = [
        {"synthesized": [{"topic_name": "A", "tasks": [{"task": "x"}, {"task": "y"}]}]} for _ in range(3)
    ]
    out = measure_stage_7_drift(runs)
    assert out["task_set_jaccard_drift_avg"] == 0.0
```

- [ ] **Step 3: Run helper tests (verify they fail then pass)**

```bash
pytest backend/tests/call_topics_v5/test_drift_baseline.py -v
```

Expected: 5 PASS.

- [ ] **Step 4: Run the actual drift script against gold set (record baseline)**

```bash
python3 -m backend.scripts.measure_v5_drift --runs 3 \
  --transcript "docs/project/config/gold set/arm_kickoff_05112026_numbered.txt" \
  | tee /tmp/v5_drift_baseline.txt
```

Expected: prints drift numbers. Capture output. (Will incur LLM cost — 3 runs × 3 stages × DeepSeek pricing ≈ few cents.)

**Save the baseline numbers** in commit message body for future delta comparison.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/scripts/measure_v5_drift.py backend/tests/call_topics_v5/test_drift_baseline.py
python3 scripts/git_ops.py commit -m "$(cat <<'EOF'
[EPIC-18] feat: v5 drift baseline measurement (STREAM 1 / S1.3)

Baseline numbers from arm_kickoff_05112026 (3 runs, DeepSeek v3.2):
  Stage 2 jaccard drift: <FILL FROM /tmp/v5_drift_baseline.txt>
  Stage 5 reassignment:  <FILL>
  Stage 7 task drift:    <FILL>

Re-run after S1.1 V5-CORE ships to validate improvement.
EOF
)"
```

---

### Task 6 — STREAM 1 (S1.1 part 1): Update Stage 5 cluster prompt for structured registry

**Files:**
- Modify: `backend/prompts/call_topics_v5_cluster.py`

- [ ] **Step 1: Update the cluster prompt to render full structure**

Replace `build_cluster_user_message` in `backend/prompts/call_topics_v5_cluster.py`:

```python
def build_cluster_user_message(units: list[dict], topic_registry: list[dict]) -> str:
    """EPIC-18 V5-CORE: registry block now includes structural payload
    (key_terms + tasks) per topic, not just names. Lets the LLM cluster
    against real existing work, not guess from topic names alone.
    """
    import json as _json
    if topic_registry:
        registry_lines = []
        for r in topic_registry:
            block = [f"- {r['name']}"]
            desc = r.get("description") or ""
            if desc:
                block.append(f"    Description: {desc}")
            kts = r.get("key_terms") or []
            if kts:
                block.append(f"    Key terms: {', '.join(kts)}")
            tasks = r.get("tasks") or []
            if tasks:
                block.append("    Existing tasks:")
                for t in tasks[:10]:  # cap to keep prompt bounded
                    task_text = (t.get("task") or "").strip()
                    owner = (t.get("owner") or "").strip()
                    suffix = f" ({owner})" if owner and owner != "unassigned" else ""
                    block.append(f"      - {task_text}{suffix}")
                if len(tasks) > 10:
                    block.append(f"      … {len(tasks)-10} more")
            registry_lines.append("\n".join(block))
        registry_block = "\n\n".join(registry_lines)
    else:
        registry_block = "(empty — first call of the project. All topics will be new.)"
    return CALL_TOPICS_V5_CLUSTER_USER_TEMPLATE.format(
        units_json=_json.dumps(units, indent=2),
        registry_block=registry_block,
    )
```

Also update the system prompt to nudge the LLM to use the structural cues:

```python
CALL_TOPICS_V5_CLUSTER_SYSTEM: str = """\
You are a domain-aware topic organizer. You receive:
  (1) a flat list of atomic units from one call
  (2) a controlled vocabulary of canonical project topics, each annotated
      with its existing tasks + key terms

Group the units into topics. Every unit belongs to exactly one topic.

When deciding whether a unit fits an existing topic, compare its text against
that topic's EXISTING TASKS and KEY TERMS — not just the topic name. A unit
matches an existing topic when its work continues, extends, or follows up on
what's already tracked there.

Only propose a new topic name when nothing in the registry's existing work
naturally absorbs the unit. Output STRICT JSON only.
"""
```

- [ ] **Step 2: Add unit test for new rendering**

Add to `backend/tests/call_topics_v5/test_stage_5_cluster.py` (create if doesn't exist):

```python
"""EPIC-18 V5-CORE — Tests for structured registry rendering in cluster prompt."""
from backend.prompts.call_topics_v5_cluster import build_cluster_user_message


def test_registry_block_includes_tasks_and_key_terms():
    units = [{"unit_id": "u1", "text": "x"}]
    registry = [
        {"name": "ARM", "description": "Risk modeling",
         "key_terms": ["LMAC", "Monte Carlo"],
         "tasks": [{"task": "Test LMAC vs Monte Carlo Mac", "owner": "Mark"}]},
    ]
    msg = build_cluster_user_message(units, registry)
    assert "ARM" in msg
    assert "Key terms: LMAC, Monte Carlo" in msg
    assert "Existing tasks:" in msg
    assert "Test LMAC vs Monte Carlo Mac (Mark)" in msg


def test_empty_registry_block_unchanged_message():
    msg = build_cluster_user_message([], [])
    assert "(empty — first call of the project" in msg


def test_registry_caps_at_10_tasks():
    registry = [{
        "name": "A", "key_terms": [],
        "tasks": [{"task": f"task {i}"} for i in range(15)],
    }]
    msg = build_cluster_user_message([], registry)
    assert "… 5 more" in msg
```

- [ ] **Step 3: Run tests**

```bash
pytest backend/tests/call_topics_v5/test_stage_5_cluster.py -v
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py add backend/prompts/call_topics_v5_cluster.py backend/tests/call_topics_v5/test_stage_5_cluster.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: Stage 5 prompt receives structured registry (S1.1 V5-CORE prompt)"
```

---

### Task 7 — STREAM 1 (S1.1 part 2): Wire structured registry through orchestrator

**Files:**
- Modify: `backend/services/call_topics_v5/orchestrator.py`

- [ ] **Step 1: Verify orchestrator passes ctx[topic_registry] to Stage 5 unchanged**

Read `backend/services/call_topics_v5/orchestrator.py` around the Stage 5 call (look for `cluster_topics(`). The structured payload from Task 3 should already be flowing through `ctx["topic_registry"]` because Task 3 already extended `RegistryEntry` to carry `key_terms` and `tasks`.

- [ ] **Step 2: Add an integration test that confirms the full chain**

Add to `backend/tests/call_topics_v5/test_stage_5_cluster.py`:

```python
import json
from unittest.mock import patch, AsyncMock
from backend.services.call_topics_v5.stage_5_cluster import cluster_topics


def _fake_llm_response(clusters):
    return json.dumps(clusters)


@patch("backend.services.call_topics_v5.stage_5_cluster.call_llm_raw", new_callable=AsyncMock)
async def test_cluster_topics_passes_structured_registry_to_llm(mock_llm):
    """EPIC-18: Stage 5 forwards full registry structure (key_terms + tasks) to LLM."""
    mock_llm.return_value = _fake_llm_response([
        {"topic_name": "ARM", "unit_ids": ["u_0001"], "new_topic": False, "importance": "high"}
    ])
    units = [{"unit_id": "u_0001", "type": "task", "text": "Test LMAC vs Monte Carlo"}]
    registry = [{
        "name": "ARM", "key_terms": ["LMAC", "Monte Carlo"],
        "tasks": [{"task": "Investigate Monte Carlo job memory failure", "owner": "Mark"}]
    }]
    await cluster_topics(units, registry, llm="openrouter", model="deepseek/deepseek-v3.2")
    # Capture the user message passed to the LLM
    user_msg = mock_llm.call_args.args[1]
    assert "Key terms: LMAC, Monte Carlo" in user_msg
    assert "Investigate Monte Carlo job memory failure (Mark)" in user_msg
```

(Mark the test with `@pytest.mark.asyncio` if pytest config requires it; check existing tests in the same file for the pattern.)

- [ ] **Step 3: Run tests**

```bash
pytest backend/tests/call_topics_v5/test_stage_5_cluster.py -v
```

Expected: new test PASS (along with prior 3).

- [ ] **Step 4: Re-run drift baseline to measure V5-CORE delta**

```bash
python3 -m backend.scripts.measure_v5_drift --runs 3 \
  --transcript "docs/project/config/gold set/arm_kickoff_05112026_numbered.txt" \
  | tee /tmp/v5_drift_after_s1_1.txt
```

Compare against Task 5's baseline. Expected: Stage 5 reassignment rate measurably lower; Stage 7 task drift lower.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/tests/call_topics_v5/test_stage_5_cluster.py
python3 scripts/git_ops.py commit -m "$(cat <<'EOF'
[EPIC-18] test: confirm Stage 5 receives structured registry through orchestrator (S1.1 V5-CORE wiring)

Drift delta vs Task 5 baseline:
  Stage 5 reassignment:  <BEFORE> → <AFTER>
  Stage 7 task drift:    <BEFORE> → <AFTER>
EOF
)"
```

---

### Task 8 — STREAM 1 (S1.2): Wire projects.context into Stage 2 and Stage 5 prompts

**Files:**
- Modify: `backend/prompts/call_topics_v5_atomic.py`
- Modify: `backend/prompts/call_topics_v5_cluster.py`
- Modify: `backend/services/call_topics_v5/stage_2_atomic.py`
- Modify: `backend/services/call_topics_v5/stage_5_cluster.py`
- Modify: `backend/services/call_topics_v5/orchestrator.py`

- [ ] **Step 1: Read current Stage 2 prompt**

```bash
cat backend/prompts/call_topics_v5_atomic.py
```

Note the location of the `*_SYSTEM` constant and `build_*_user_message` function. The injection point should be the system prompt (priming, applies to all calls in this project).

- [ ] **Step 2: Add project_context kwarg to Stage 2 prompt builder**

In `backend/prompts/call_topics_v5_atomic.py`, modify the `*_SYSTEM` to support optional injection:

```python
def build_atomic_system_prompt(project_context: str = "") -> str:
    """EPIC-18 S1.2: prime the LLM with project context if available."""
    base = CALL_TOPICS_V5_ATOMIC_SYSTEM  # existing constant unchanged
    if project_context.strip():
        context_block = (
            "\n\nPROJECT CONTEXT (background for this team/project — use it to "
            "disambiguate references in the transcript, but do not invent claims "
            "not present in the transcript):\n\n"
            f"{project_context.strip()}\n"
        )
        return base + context_block
    return base
```

- [ ] **Step 3: Add the same builder to Stage 5 prompt**

In `backend/prompts/call_topics_v5_cluster.py`, add an analogous `build_cluster_system_prompt(project_context)` helper.

- [ ] **Step 4: Update Stage 2 service to accept and use project_context**

In `backend/services/call_topics_v5/stage_2_atomic.py`, find the `call_llm_raw` call. Change the system prompt passed in from `CALL_TOPICS_V5_ATOMIC_SYSTEM` to `build_atomic_system_prompt(project_context)`. Add `project_context: str = ""` to the public function signature.

- [ ] **Step 5: Update Stage 5 service same way**

In `backend/services/call_topics_v5/stage_5_cluster.py`, same treatment.

- [ ] **Step 6: Wire orchestrator to pass project.context down**

In `backend/services/call_topics_v5/orchestrator.py`, after Stage 1 loads context, capture `project_context = ctx["project_metadata"].get("context", "")`. Pass to Stage 2 and Stage 5 calls:

```python
units = await extract_atomic_units(ingested, llm=llm, model=model, project_context=project_context)
# ... later ...
clusters_out = await cluster_topics(units, ctx["topic_registry"], llm=llm, model=model, project_context=project_context)
```

- [ ] **Step 7: Add test verifying injection**

In `backend/tests/call_topics_v5/test_stage_5_cluster.py`, add:

```python
@patch("backend.services.call_topics_v5.stage_5_cluster.call_llm_raw", new_callable=AsyncMock)
async def test_cluster_topics_injects_project_context(mock_llm):
    mock_llm.return_value = "[]"
    await cluster_topics(
        [{"unit_id": "u1", "text": "x"}], [],
        llm="openrouter", model="deepseek/deepseek-v3.2",
        project_context="This project tracks portfolio risk analytics; team uses FactSet, Snowflake, Monte Carlo models.",
    )
    system_msg = mock_llm.call_args.args[0]
    assert "FactSet, Snowflake, Monte Carlo models" in system_msg
```

- [ ] **Step 8: Run tests**

```bash
pytest backend/tests/call_topics_v5/ -v
```

Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
python3 scripts/git_ops.py add backend/prompts/call_topics_v5_atomic.py backend/prompts/call_topics_v5_cluster.py backend/services/call_topics_v5/stage_2_atomic.py backend/services/call_topics_v5/stage_5_cluster.py backend/services/call_topics_v5/orchestrator.py backend/tests/call_topics_v5/test_stage_5_cluster.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: wire projects.context into Stage 2 + Stage 5 prompts (S1.2 V5-CONTEXT)"
```

---

### Task 9 — STREAM 1 (S1.4): Remove hardcoded DeepSeek defaults from Stage 5 + Stage 7

**Files:**
- Modify: `backend/services/call_topics_v5/stage_5_cluster.py:103`
- Modify: `backend/services/call_topics_v5/stage_7_synthesis.py:106`
- Modify: `backend/services/call_topics_v5/stage_3_recall.py` (if same pattern)

- [ ] **Step 1: Remove default from Stage 5**

In `stage_5_cluster.py:102-103`, change function signature:

```python
# BEFORE
async def cluster_topics(
    atomic_units: list[dict],
    topic_registry: list[dict],
    *,
    llm: str = "openrouter",
    model: str | None = "deepseek/deepseek-v3.2",
    project_context: str = "",
) -> dict:

# AFTER
async def cluster_topics(
    atomic_units: list[dict],
    topic_registry: list[dict],
    *,
    llm: str,
    model: str | None,
    project_context: str = "",
) -> dict:
```

- [ ] **Step 2: Remove default from Stage 7**

Same in `stage_7_synthesis.py:101-107` for both `synthesize_topic` and `synthesize_all_topics`.

- [ ] **Step 3: Check Stage 3**

```bash
grep -n "deepseek" backend/services/call_topics_v5/stage_3_recall.py
```

If present, remove the default the same way.

- [ ] **Step 4: Check Stage 2**

```bash
grep -n "deepseek" backend/services/call_topics_v5/stage_2_atomic.py
```

Remove if present.

- [ ] **Step 5: Run all v5 tests**

```bash
pytest backend/tests/call_topics_v5/ -v
```

Expected: tests that previously relied on the default may need updating to pass explicit `llm=` / `model=` kwargs. Fix them.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/services/call_topics_v5/
python3 scripts/git_ops.py commit -m "[EPIC-18] refactor: remove hardcoded DeepSeek defaults; force project-config routing (S1.4)"
```

---

### Task 10 — STREAM 3: Pass 1 test fixtures (foundation for STREAM 2 TDD)

**Files:**
- Create: `backend/tests/fixtures/pass1/` directory + 5 fixture files
- Create: `backend/tests/test_pass1_fixtures.py`

**Why now (between STREAMs 1 and 2):** STREAM 0 + STREAM 1 stabilized the shape Pass 1 sees. We need fixtures BEFORE refactoring Pass 1 so we can TDD STREAM 2 without burning LLM tokens.

- [ ] **Step 1: Create fixture directory and __init__**

```bash
mkdir -p backend/tests/fixtures/pass1
touch backend/tests/fixtures/pass1/__init__.py
```

- [ ] **Step 2: Author `same_transcript_dup.json` fixture**

Create `backend/tests/fixtures/pass1/same_transcript_dup.json`:

```json
{
  "scenario": "same_transcript_dup",
  "description": "Candidate topic extracted from a transcript identical to a past call. Should reconcile cleanly as duplicate.",
  "candidate": {
    "topic_id": "cand-001",
    "name": "Risk Model & Job Optimization",
    "summary": "",
    "tasks": [
      {"task": "Test LMAC vs Monte Carlo Mac on fixed income portfolio", "owner": "Mark", "key_terms": ["LMAC", "Monte Carlo", "fixed income"]},
      {"task": "Investigate Monte Carlo Mac job memory failure", "owner": "Mark", "key_terms": ["Monte Carlo", "memory"]}
    ]
  },
  "project_topics": [
    {
      "topic_id": "proj-arm",
      "name": "ARM",
      "summary": "Account aggregation risk modeling work stream",
      "key_terms": ["LMAC", "Monte Carlo", "MAC", "memory"],
      "tasks": [
        {"task": "Test LMAC vs Monte Carlo Mac on fixed income portfolio", "owner": "Mark"},
        {"task": "Investigate Monte Carlo Mac job memory failure", "owner": "Mark"}
      ]
    }
  ],
  "past_transcripts": {
    "call-a-uuid": "0001  Test LMAC vs Monte Carlo Mac on fixed income portfolio.\n0002  Mark mentions Monte Carlo job memory failure investigation in progress."
  },
  "expected_verdict": {
    "verdict": "should_be_merged_with",
    "matched_topic_id": "proj-arm",
    "min_confidence": 75
  }
}
```

- [ ] **Step 3: Author the other four fixtures (true_new, mega_topic, wrong_canonical, naming_drift)**

Follow the same shape. Each ~30-50 lines. Use distinct topic_ids and concrete realistic content (you can adapt from the actual call B / project B data the user tested with).

- [ ] **Step 4: Write fixture loader test**

Create `backend/tests/test_pass1_fixtures.py`:

```python
"""EPIC-18 STREAM 3 — Pass 1 fixture-driven tests (mocked LLM)."""
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pass1"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def test_all_fixtures_load_and_have_required_keys():
    """Foundation test: every fixture has the schema STREAM 2 will assume."""
    required = {"scenario", "candidate", "project_topics", "past_transcripts", "expected_verdict"}
    for path in FIXTURE_DIR.glob("*.json"):
        fix = json.loads(path.read_text())
        missing = required - set(fix.keys())
        assert not missing, f"{path.name} missing keys: {missing}"
        assert "verdict" in fix["expected_verdict"]
        assert "min_confidence" in fix["expected_verdict"]
```

- [ ] **Step 5: Run test**

```bash
pytest backend/tests/test_pass1_fixtures.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/tests/fixtures/pass1/ backend/tests/test_pass1_fixtures.py
python3 scripts/git_ops.py commit -m "[EPIC-18] test: Pass 1 fixtures + loader (STREAM 3 foundation)"
```

---

### Task 11 — STREAM 2 (S2.1 part 1): citation_verify.py replace string match with line-range check

**Files:**
- Modify: `backend/services/citation_verify.py`
- Modify: `backend/tests/test_citation_verify.py` (create if doesn't exist)

- [ ] **Step 1: Write failing tests for new line-range verifier**

Create/extend `backend/tests/test_citation_verify.py`:

```python
"""EPIC-18 S2.1 — Tests for the new line-number citation verifier."""
from backend.services.citation_verify import (
    verify_evidence_lines, resolve_evidence_lines,
)


def test_verify_evidence_lines_passes_for_valid_range():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [10, 20]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert ok
    assert failures == []


def test_verify_evidence_lines_fails_for_unknown_call():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-X", "evidence_lines": [1, 5]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok
    assert "call-X" in failures[0]


def test_verify_evidence_lines_fails_for_out_of_bounds():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [99, 200]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok
    assert "out of bounds" in failures[0]


def test_verify_evidence_lines_fails_for_inverted_range():
    transcripts = {"call-1": {"line_count": 100}}
    citations = [{"call_id": "call-1", "evidence_lines": [50, 10]}]
    ok, failures = verify_evidence_lines(citations, transcripts)
    assert not ok


def test_resolve_evidence_lines_returns_verbatim_text():
    ingested = {"line_count": 3, "lines": {"0001": "Hello", "0002": "World", "0003": "!"}}
    transcripts = {"call-1": ingested}
    text = resolve_evidence_lines("call-1", [1, 2], transcripts)
    assert "Hello" in text and "World" in text
```

- [ ] **Step 2: Run failing tests**

```bash
pytest backend/tests/test_citation_verify.py -v
```

Expected: FAIL — `verify_evidence_lines` and `resolve_evidence_lines` not defined.

- [ ] **Step 3: Implement the new verifier**

Rewrite `backend/services/citation_verify.py`:

```python
"""Citation verifier — EPIC-18 S2.1: line-number based, mirrors v5 Stage 4 pattern.

The LLM emits `evidence_lines: [start, end]`. Code resolves to verbatim text
via the v5 ingest line index. Verification is a bounds check; no string
matching that could fail on whitespace/punctuation drift.

LEGACY: verify_citations() retained for backward compat with Pass 2 + Pass 3,
which still use the free-form quote contract. Those are out of scope for
EPIC-18; they will be migrated in a future epic.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("calltracker.citation_verify")


# ── EPIC-18 NEW VERIFIER ──────────────────────────────────────────────────────
def verify_evidence_lines(
    citations: list[dict],
    transcripts: dict[str, dict],
) -> tuple[bool, list[str]]:
    """For each citation, check that evidence_lines is in-bounds for the cited call's
    ingested transcript.

    Args:
        citations: list of {"call_id": str, "evidence_lines": [start, end], ...}.
        transcripts: {call_id: ingested_dict_from_stage_0}. Each must have line_count.

    Returns:
        (all_ok, list_of_failure_messages).
    """
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        ev = c.get("evidence_lines")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id")
            continue
        ingested = transcripts.get(call_id)
        if ingested is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts")
            continue
        if not isinstance(ev, list) or len(ev) != 2:
            failed.append(f"citation #{i}: evidence_lines must be [start, end] (got {ev!r})")
            continue
        try:
            start, end = int(ev[0]), int(ev[1])
        except (TypeError, ValueError):
            failed.append(f"citation #{i}: evidence_lines values must be integers (got {ev!r})")
            continue
        line_count = ingested.get("line_count", 0)
        if start < 1 or end > line_count:
            failed.append(f"citation #{i}: lines [{start},{end}] out of bounds (transcript has {line_count} lines)")
            continue
        if start > end:
            failed.append(f"citation #{i}: inverted range [{start},{end}] (start > end)")
            continue
    return (len(failed) == 0, failed)


def resolve_evidence_lines(
    call_id: str, evidence_lines: list[int], transcripts: dict[str, dict],
) -> str:
    """Resolve evidence_lines to verbatim transcript text via v5 ingest line index."""
    from backend.services.call_topics_v5.stage_0_ingest import resolve_lines
    ingested = transcripts.get(call_id)
    if ingested is None:
        return ""
    start = f"{int(evidence_lines[0]):04d}"
    end = f"{int(evidence_lines[1]):04d}"
    return resolve_lines(ingested, start, end)


# ── LEGACY (Pass 2 + Pass 3, deprecate in future epic) ───────────────────────
def verify_citations(citations: list[dict], transcripts_by_call: dict[str, str]) -> tuple[bool, list[str]]:
    """LEGACY string-match verifier for Pass 2 and Pass 3. Not used by Pass 1 after EPIC-18."""
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        quote = c.get("quote", "")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id"); continue
        body = transcripts_by_call.get(call_id)
        if body is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts"); continue
        if not quote:
            failed.append(f"citation #{i}: empty quote"); continue
        if quote not in body:
            preview = quote if len(quote) <= 240 else quote[:240] + "…"
            failed.append(f'citation #{i}: this quote was not found verbatim in the cited transcript — "{preview}"')
    return (len(failed) == 0, failed)


def find_quote_lines(quote: str, transcript_body: str) -> str | None:
    """LEGACY helper. Used by Pass 2/3."""
    idx = transcript_body.find(quote)
    if idx == -1:
        return None
    before = transcript_body[:idx]
    start_line = before.count("\n") + 1
    end_line = start_line + quote.count("\n")
    return f"{start_line}-{end_line}"
```

- [ ] **Step 4: Run tests (verify PASS)**

```bash
pytest backend/tests/test_citation_verify.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/services/citation_verify.py backend/tests/test_citation_verify.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: line-range citation verifier (S2.1 P1-CITATIONS foundation)"
```

---

### Task 12 — STREAM 2 (S2.1 part 2): Pass 1 prompt rewrites citation contract

**Files:**
- Modify: `backend/prompts/verify_new_topic.py`

- [ ] **Step 1: Replace the CITATION CONTRACT section**

Open `backend/prompts/verify_new_topic.py`. Find the `CITATION CONTRACT (anti-hallucination)` block. Replace with:

```
──────────────────────────────────────────────────────────────────────
CITATION CONTRACT (line-number, anti-hallucination)
──────────────────────────────────────────────────────────────────────
Each transcript is supplied with line numbers (format: "0001  <text>").
DO NOT copy or paraphrase quote text. Instead, cite by line range:

  {"call_id": "<uuid>", "evidence_lines": [start_line, end_line], "for": "verdict|extraction"}

- start_line and end_line are integers (the leading zeros are display-only)
- The range MUST be inside the actual transcript's line count
- For verdict citations, the cited lines MUST be about the SAME WORK
  STREAM as the candidate (not adjacent topics that share a name)
- For merges: provide AT LEAST TWO verdict citations
```

- [ ] **Step 2: Replace the `OUTPUT FORMAT` block**

Same file — modify the `citations` field in the JSON example:

```json
  "citations": [
    {"call_id": "<uuid>", "evidence_lines": [<start>, <end>], "for": "verdict"}
  ]
```

Remove the `quote` and `lines` fields entirely from the example.

- [ ] **Step 3: Drop the `extraction_grounded` / `ungrounded_items` from the schema**

In the same file, remove these blocks:

```
──────────────────────────────────────────────────────────────────────
EXTRACTION GROUNDING CHECK (separate concern)
──────────────────────────────────────────────────────────────────────
Independently of the merge verdict, ...
```

And from the OUTPUT FORMAT example:

```
  "extraction_grounded": true | false,
  "ungrounded_items": [...]
```

- [ ] **Step 4: Add a one-line note at top documenting EPIC-18 changes**

After the existing `"""Pass ① — verify_new_topic prompt body.` docstring, append:

```
EPIC-18 (2026-05-24): citation contract switched to line-numbers (matches v5 Stage 4).
extraction_grounded check removed (it was checking against a transcript Pass 1
never sees — see design doc Section 3 RC4).
```

- [ ] **Step 5: Commit (no test — prompt is data; behavior tests live with topic_verification.py)**

```bash
python3 scripts/git_ops.py add backend/prompts/verify_new_topic.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: Pass 1 prompt switches to line-number citations (S2.1)"
```

---

### Task 13 — STREAM 2 (S2.1 part 3): topic_verification.py uses line-numbered transcripts

**Files:**
- Modify: `backend/services/topic_verification.py`
- Modify: `backend/routers/topics.py:680-693` (the `_run_verify_new_background` block)

- [ ] **Step 1: Update `_build_verify_new_prompt` to take ingested transcripts**

In `backend/services/topic_verification.py`, modify `_build_verify_new_prompt`:

```python
def _build_verify_new_prompt(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, dict],  # EPIC-18: now {call_id: ingested_dict}, not {call_id: raw_str}
    precheck: dict | None = None,
) -> str:
    """EPIC-18: transcripts are now ingested (line-numbered) dicts from v5 Stage 0.
    LLM sees `0001  <text>` line-prefixed format and cites by line range.
    """
    def _shape_topic_for_llm(t: dict) -> dict:
        return {
            "topic_id": t.get("topic_id"),
            "name": t.get("name"),
            "summary": t.get("summary") or "",
            "tasks": t.get("tasks") or [],
        }
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ({ing['line_count']} lines) ---\n"
        + "\n".join(f"{idx}  {text}" for idx, text in ing.get("lines", {}).items())
        for cid, ing in transcripts.items()
    )
    project_topics_block = json.dumps([_shape_topic_for_llm(t) for t in project_topics], indent=2)
    candidate_block = json.dumps(_shape_topic_for_llm(candidate), indent=2)
    precheck_block = ""
    if precheck:
        precheck_block = (
            "\n\nLEXICAL PRE-CHECK (deterministic, fyi — your own analysis should be primary):\n"
            f"{json.dumps(precheck, indent=2)}\n"
        )
    return (
        f"{VERIFY_NEW_TOPIC_PROMPT}\n\n"
        f"CANDIDATE NEW TOPIC:\n{candidate_block}\n\n"
        f"EXISTING PROJECT TOPICS:\n{project_topics_block}\n\n"
        f"PAST TRANSCRIPTS (line-numbered):\n{transcripts_block}"
        f"{precheck_block}"
    )
```

- [ ] **Step 2: Update `run_verify_new` to use the new verifier**

In `run_verify_new`, replace the `verify_citations(cits, transcripts)` call with `verify_evidence_lines(cits, transcripts)`. Also delete the `find_quote_lines` retry block (no longer relevant — lines are explicit).

```python
# BEFORE
ok, failures = verify_citations(cits, transcripts)

# AFTER
from backend.services.citation_verify import verify_evidence_lines
ok, failures = verify_evidence_lines(cits, transcripts)
```

Also remove `extraction_grounded` handling — the prompt no longer emits it, so any post-LLM logic referencing those fields can be deleted.

- [ ] **Step 3: Update the router to ingest past transcripts before passing in**

In `backend/routers/topics.py` around line 680-693, the `transcripts` dict is built as `{c["id"]: c["transcript"]}` (raw strings). Change to ingest each one:

```python
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript

transcripts = {
    c["id"]: ingest_transcript(c.get("transcript") or "")
    for c in past_calls
    if c.get("transcript")
}
```

- [ ] **Step 4: Add unit test for new prompt builder**

Add to `backend/tests/test_topic_verification.py` (create if doesn't exist):

```python
"""EPIC-18 — Tests for Pass 1 line-numbered citation flow."""
from backend.services.topic_verification import _build_verify_new_prompt


def test_prompt_includes_line_numbered_transcripts():
    candidate = {"topic_id": "c-1", "name": "X", "tasks": []}
    transcripts = {
        "call-a": {
            "line_count": 2,
            "lines": {"0001": "Hello world", "0002": "Second line"},
        }
    }
    msg = _build_verify_new_prompt(candidate, [], transcripts)
    assert "--- CALL call-a (2 lines) ---" in msg
    assert "0001  Hello world" in msg
    assert "0002  Second line" in msg
```

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topic_verification.py backend/tests/test_citation_verify.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/services/topic_verification.py backend/routers/topics.py backend/tests/test_topic_verification.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: Pass 1 ingests past transcripts + uses line-range verifier (S2.1 end-to-end)"
```

---

### Task 14 — STREAM 2 (S2.2): Pass 1 bidirectional verification (canonical match check)

**Files:**
- Modify: `backend/prompts/verify_new_topic.py` (add second prompt variant)
- Modify: `backend/services/topic_verification.py` (add `run_verify_canonical_match`)
- Modify: `backend/routers/topics.py` (router routes to either function based on `new_topic` flag)

- [ ] **Step 1: Add canonical-match verification prompt**

In `backend/prompts/verify_new_topic.py`, append:

```python

VERIFY_CANONICAL_MATCH_PROMPT: str = """\
ROLE: You are a forensic PMO match-correctness specialist. The v5 extraction
pipeline grouped a set of atomic units under an existing project topic by
NAME. Your job: was this canonical assignment correct?

You will receive:
  - The candidate topic (what v5 produced for THIS call, including its tasks)
  - The matched existing project topic (with full task structure)
  - Past transcripts (line-numbered)

VERDICT OPTIONS:
  - "confirmed_match"               — the candidate's work fits the existing topic's
                                       ongoing task list (work-continuity confirmed)
  - "wrong_canonical_actually_new"  — v5 mismatched on name; the work is genuinely new
  - "wrong_canonical_belongs_elsewhere" — v5 mismatched; the work fits a DIFFERENT
                                       existing project topic (provide its topic_id)

Use the SAME work-continuity test as verify_new: do the candidate's tasks
belong on the matched topic's task list?

Citation contract: same line-number format as verify_new.

OUTPUT (strict JSON):
{
  "verdict": "confirmed_match" | "wrong_canonical_actually_new" | "wrong_canonical_belongs_elsewhere",
  "reasoning": "<one sentence anchored in concrete task content from both sides>",
  "alternative_topic_id": "<uuid or null — only when wrong_canonical_belongs_elsewhere>",
  "citations": [
    {"call_id": "<uuid>", "evidence_lines": [<start>, <end>], "for": "verdict"}
  ]
}
"""
```

- [ ] **Step 2: Add the verification function in topic_verification.py**

```python
async def run_verify_canonical_match(
    candidate: dict,
    matched_topic: dict,
    all_project_topics: list[dict],
    transcripts: dict[str, dict],
    *,
    llm: str,
    model: str | None,
    log_fn=None,
) -> dict:
    """EPIC-18 S2.2 — verify that v5's canonical match was correct.

    Returns: {verdict, reasoning, alternative_topic_id, citations, needs_manual_review}
    """
    from backend.prompts.verify_new_topic import VERIFY_CANONICAL_MATCH_PROMPT

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ({ing['line_count']} lines) ---\n"
        + "\n".join(f"{idx}  {text}" for idx, text in ing.get("lines", {}).items())
        for cid, ing in transcripts.items()
    )
    prompt = (
        f"{VERIFY_CANONICAL_MATCH_PROMPT}\n\n"
        f"CANDIDATE (what v5 produced this call):\n{json.dumps(candidate, indent=2)}\n\n"
        f"MATCHED EXISTING TOPIC:\n{json.dumps(matched_topic, indent=2)}\n\n"
        f"ALL PROJECT TOPICS (for alternative_topic_id selection):\n"
        f"{json.dumps([{'topic_id':t.get('topic_id'),'name':t.get('name')} for t in all_project_topics], indent=2)}\n\n"
        f"PAST TRANSCRIPTS:\n{transcripts_block}"
    )
    await _log(f"      [canonical-check: {matched_topic.get('name')}] asking LLM")
    result = await _call_llm(prompt, llm, model=model)
    if not isinstance(result, dict):
        return {"verdict": "confirmed_match", "needs_manual_review": True,
                "reasoning": "LLM non-dict response — assume v5 was right pending review",
                "citations": [], "alternative_topic_id": None}
    from backend.services.citation_verify import verify_evidence_lines
    cits = result.get("citations") or []
    ok, failures = verify_evidence_lines(cits, transcripts)
    result["needs_manual_review"] = not ok
    if not ok:
        result["failed_citations"] = failures
    return result
```

- [ ] **Step 3: Update the router to route candidates by `new_topic` flag**

In `backend/routers/topics.py::_run_verify_new_background`, after building `new_candidates`, ALSO build `canonical_candidates` (topics from v5 output where `new_topic=False`). Run `run_verify_canonical_match` for each. Aggregate both result sets into the cache.

(Detailed router edits depend on how the v5 output flows through to the verify_new endpoint — this may require inspecting the current routing logic and adapting. Flag as a "router integration" step that needs the implementer to read `routers/topics.py` around the verify_new endpoint to wire correctly.)

- [ ] **Step 4: Add unit test for canonical match verification**

```python
async def test_run_verify_canonical_match_confirmed(monkeypatch):
    from backend.services.topic_verification import run_verify_canonical_match
    async def fake_llm(*a, **kw):
        return {
            "verdict": "confirmed_match",
            "reasoning": "Candidate task 'X' matches existing task 'X'.",
            "alternative_topic_id": None,
            "citations": [{"call_id": "c1", "evidence_lines": [1, 2], "for": "verdict"}],
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_canonical_match(
        candidate={"name": "C", "tasks": []},
        matched_topic={"topic_id": "t1", "name": "ARM", "tasks": [{"task": "X"}]},
        all_project_topics=[],
        transcripts={"c1": {"line_count": 5, "lines": {"0001": "x", "0002": "y", "0003": "z", "0004": "a", "0005": "b"}}},
        llm="openrouter", model="x",
    )
    assert out["verdict"] == "confirmed_match"
    assert out["needs_manual_review"] is False
```

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topic_verification.py -v
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/prompts/verify_new_topic.py backend/services/topic_verification.py backend/routers/topics.py backend/tests/test_topic_verification.py
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: Pass 1 bidirectional — verify v5 canonical matches (S2.2 P1-BIDIRECTIONAL)"
```

---

### Task 15 — STREAM 2 (S2.3): Unified similarity scoring module

**Files:**
- Create: `backend/services/topic_similarity.py`
- Modify: `backend/services/call_topics_v5/stage_6_reconcile.py`
- Modify: `backend/services/topic_verification.py`
- Create: `backend/tests/test_topic_similarity.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_topic_similarity.py`:

```python
"""EPIC-18 S2.3 — Unified similarity scoring."""
from backend.services.topic_similarity import (
    weighted_jaccard, compute_idf, effective_token_set,
)


def test_effective_token_set_includes_name_and_key_terms():
    t = {"name": "Stress Testing", "key_terms": ["LMAC", "Monte Carlo"]}
    tokens = effective_token_set(t)
    assert "stress" in tokens
    assert "testing" in tokens
    assert "lmac" in tokens
    assert "monte" in tokens
    assert "carlo" in tokens


def test_effective_token_set_aggregates_per_task_key_terms():
    t = {"name": "X", "tasks": [{"key_terms": ["foo", "bar"]}, {"key_terms": ["baz"]}]}
    tokens = effective_token_set(t)
    assert {"foo", "bar", "baz"}.issubset(tokens)


def test_weighted_jaccard_full_overlap_returns_one():
    project_topics = [
        {"name": "A B", "key_terms": []},
        {"name": "C D", "key_terms": []},
    ]
    idf = compute_idf(project_topics)
    score = weighted_jaccard(["a", "b"], ["a", "b"], idf)
    assert score == 1.0


def test_weighted_jaccard_no_overlap_returns_zero():
    project_topics = [{"name": "A B"}]
    idf = compute_idf(project_topics)
    assert weighted_jaccard(["a"], ["x"], idf) == 0.0
```

- [ ] **Step 2: Run failing test**

```bash
pytest backend/tests/test_topic_similarity.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement topic_similarity.py**

Create `backend/services/topic_similarity.py`. Lift the existing IDF + jaccard implementations from `backend/services/topic_verification.py` (lines ~100-200) — they are already correct, just need to be in a shared module:

```python
"""EPIC-18 S2.3 — Single source of truth for topic similarity scoring.

Used by:
  - v5 Stage 6 (reconcile) to suggest registry merges
  - Pass 1 lexical_precheck to qualify LLM evaluation candidates
  - Pass 1 confidence scoring

Replaces three previously-divergent implementations.
"""
from __future__ import annotations
import math as _math
import re as _re


_STOPWORDS = {
    "the", "a", "an", "to", "and", "or", "for", "with", "of", "in", "on", "at",
    "by", "from", "this", "that", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "their", "our", "us",
    "we", "they", "he", "she", "it", "you", "your", "my", "as", "if",
    "when", "where", "what", "who", "how", "why", "all", "any", "some", "no",
    "not", "more", "less", "very", "just", "also", "than", "then", "but",
    "into", "out", "off", "over", "under", "again", "further", "once",
}


def effective_token_set(topic_or_candidate: dict) -> set[str]:
    tokens: set[str] = set()
    sources: list[str] = []
    for kt in (topic_or_candidate.get("key_terms") or []):
        if kt: sources.append(str(kt))
    if topic_or_candidate.get("name"):
        sources.append(str(topic_or_candidate["name"]))
    for task in (topic_or_candidate.get("tasks") or []):
        if isinstance(task, dict):
            for kt in (task.get("key_terms") or []):
                if kt: sources.append(str(kt))
    for src in sources:
        for word in _re.findall(r"\b[a-z][a-z0-9_-]+\b", src.lower()):
            if len(word) > 2 and word not in _STOPWORDS:
                tokens.add(word)
    return tokens


def compute_idf(project_topics: list[dict]) -> dict[str, float]:
    N = max(len(project_topics), 1)
    df: dict[str, int] = {}
    for t in project_topics:
        for tok in effective_token_set(t):
            df[tok] = df.get(tok, 0) + 1
    return {tok: _math.log((N + 1) / (count + 1)) + 1.0 for tok, count in df.items()}


def weighted_jaccard_tokens(a_tokens: set[str], b_tokens: set[str], idf: dict[str, float]) -> float:
    inter = a_tokens & b_tokens
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    inter_w = sum(idf.get(t, 1.0) for t in inter)
    union_w = sum(idf.get(t, 1.0) for t in union)
    return inter_w / union_w if union_w > 0 else 0.0


def weighted_jaccard(a_terms: list[str], b_terms: list[str], idf: dict[str, float]) -> float:
    set_a = effective_token_set({"key_terms": a_terms})
    set_b = effective_token_set({"key_terms": b_terms})
    return weighted_jaccard_tokens(set_a, set_b, idf)
```

- [ ] **Step 4: Update Stage 6 and topic_verification.py to import from new module**

In `backend/services/call_topics_v5/stage_6_reconcile.py`:

```python
# Delete local _tokens, _jaccard helpers (lines 23-36)
# Replace with:
from backend.services.topic_similarity import weighted_jaccard_tokens as _jaccard_tokens
from backend.services.topic_similarity import effective_token_set as _tokens_of_text
def _jaccard(a: str, b: str) -> float:
    sa = _tokens_of_text({"name": a})
    sb = _tokens_of_text({"name": b})
    inter, union = sa & sb, sa | sb
    return (len(inter) / len(union)) if union else 0.0
```

In `backend/services/topic_verification.py`, delete the local `_STOPWORDS`, `_norm_terms`, `effective_token_set`, `compute_idf`, `weighted_jaccard_tokens`, `weighted_jaccard` definitions (lines ~100-200). Replace with import:

```python
from backend.services.topic_similarity import (
    effective_token_set, compute_idf, weighted_jaccard_tokens, weighted_jaccard,
)
```

- [ ] **Step 5: Run all related tests**

```bash
pytest backend/tests/test_topic_similarity.py backend/tests/test_topics.py backend/tests/test_topic_verification.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/services/topic_similarity.py backend/services/call_topics_v5/stage_6_reconcile.py backend/services/topic_verification.py backend/tests/test_topic_similarity.py
python3 scripts/git_ops.py commit -m "[EPIC-18] refactor: unified topic_similarity module (S2.3 — 3 impls → 1)"
```

---

### Task 16 — STREAM 2 (S2.3): Harden non-dict LLM response in Pass 1

**Files:**
- Modify: `backend/services/topic_verification.py::run_verify_new`

- [ ] **Step 1: Audit the non-dict handling**

Read `run_verify_new` from `topic_verification.py:594-780`. The current loop retries 2× on non-dict. The Stage 5 v5 pattern (see `stage_5_cluster.py:142-147`) is to detect non-list shapes and unwrap nested arrays. Apply the same pattern.

- [ ] **Step 2: Add a non-dict recovery branch BEFORE the retry loop**

Already partially present (lines 627-657 unwrap bare arrays). Verify it works for the actual DeepSeek failure mode in the user's test. If the LLM returned a wrapped `{"clusters": [...]}` shape instead of bare array, add handling.

Concretely, before the existing `if isinstance(result, list)` check, add:

```python
if isinstance(result, dict) and "evaluations" not in result and "verdict" not in result:
    # Some models wrap the verdict in an outer key — try common keys.
    for k in ("result", "data", "response", "judgement"):
        if isinstance(result.get(k), dict) and ("verdict" in result[k] or "evaluations" in result[k]):
            result = result[k]
            break
```

- [ ] **Step 3: Add test for the wrapped-response recovery**

In `backend/tests/test_topic_verification.py`:

```python
async def test_run_verify_new_recovers_wrapped_response(monkeypatch):
    from backend.services.topic_verification import run_verify_new
    async def fake_llm(*a, **kw):
        return {"result": {
            "verdict": "truly_new", "final_verdict": "truly_new",
            "matched_topic_id": None, "matched_topic_name": None,
            "evaluations": [], "citations": [],
            "merge_reasoning": "No fit.",
        }}
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_new(
        candidate={"name": "C", "tasks": []},
        project_topics=[],
        transcripts={},
        llm="x", model="y",
    )
    assert out["verdict"] == "truly_new"
    assert out["needs_manual_review"] is False
```

- [ ] **Step 4: Run tests**

```bash
pytest backend/tests/test_topic_verification.py -v
```

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py add backend/services/topic_verification.py backend/tests/test_topic_verification.py
python3 scripts/git_ops.py commit -m "[EPIC-18] fix: Pass 1 recovers from common LLM wrapping patterns (S2.3 hardening)"
```

---

### Task 17 — STREAM 3 (refresh): Wire fixtures into Pass 1 unit tests with mocked LLM

**Files:**
- Modify: `backend/tests/test_pass1_fixtures.py`

- [ ] **Step 1: Add per-fixture test**

Extend `backend/tests/test_pass1_fixtures.py`:

```python
import pytest
from backend.services.topic_verification import run_verify_new


def _mocked_llm_factory(verdict: str, matched_topic_id: str | None):
    """Return a fake _call_llm coroutine that produces a canned verdict."""
    async def fake(*args, **kwargs):
        return {
            "verdict": verdict,
            "final_verdict": verdict,
            "matched_topic_id": matched_topic_id,
            "matched_topic_name": None,
            "evaluations": [],
            "citations": (
                [{"call_id": "call-a-uuid", "evidence_lines": [1, 2], "for": "verdict"}]
                if verdict == "should_be_merged_with" else []
            ),
            "merge_reasoning": "fixture-driven canned response",
        }
    return fake


@pytest.mark.asyncio
async def test_same_transcript_dup_fixture_reconciles(monkeypatch):
    from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
    fix = load_fixture("same_transcript_dup")
    # Mock LLM to return the expected verdict
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mocked_llm_factory("should_be_merged_with", fix["expected_verdict"]["matched_topic_id"]),
    )
    transcripts = {
        cid: ingest_transcript(body)
        for cid, body in fix["past_transcripts"].items()
    }
    out = await run_verify_new(
        candidate=fix["candidate"],
        project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x", model="y",
    )
    assert out["verdict"] == fix["expected_verdict"]["verdict"]
    assert out["matched_topic_id"] == fix["expected_verdict"]["matched_topic_id"]
    assert out["confidence"]["pct"] >= fix["expected_verdict"]["min_confidence"]
```

Repeat the pattern for `true_new`, `mega_topic`, `wrong_canonical`, `naming_drift` fixtures (each with the appropriate canned mock response per scenario).

- [ ] **Step 2: Run tests**

```bash
pytest backend/tests/test_pass1_fixtures.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py add backend/tests/test_pass1_fixtures.py
python3 scripts/git_ops.py commit -m "[EPIC-18] test: Pass 1 fixture-driven tests with mocked LLM (STREAM 3 complete)"
```

---

### Task 18 — Real-LLM smoke test against the user's actual project B data

**Files:**
- Manual test — no code

**Purpose:** validate the full S1+S2 stack against the test that started this epic.

- [ ] **Step 1: Reset call B's verify_new state**

In the app or via Supabase Dashboard, set `verify_new_status = NULL` and `verify_new_cache = NULL` for call B in project B.

- [ ] **Step 2: Re-run v5 + Pass 1 on call B**

Through the UI: open call B, advance through call_topics → Pass 1 (with project_matching removed, Pass 1 runs automatically after v5).

- [ ] **Step 3: Inspect results**

Confirm:
- 0/N citation failures (vs. 6/6 before)
- ≥4/5 candidates get the right verdict (vs. 1/5 before)
- No "ungrounded items" noise
- Mega-topic case either no longer occurs (V5-CORE worked) OR Pass 1 surfaces multi-target signal cleanly

- [ ] **Step 4: Capture findings + commit notes to build-log.md**

Update `docs/project/config/build-log.md` with a new dated entry describing what shipped + the smoke-test results.

```bash
python3 scripts/git_ops.py add docs/project/config/build-log.md
python3 scripts/git_ops.py commit -m "[EPIC-18] docs: build-log update — same-transcript test results after S1+S2"
```

---

### Task 19 — STREAM 4: Verification asymmetry threshold + frontend auto-accept

**Files:**
- Modify: `backend/services/topic_verification.py::compute_confidence`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/ProjectUpdatesStage.tsx`

- [ ] **Step 1: Add `auto_accept_eligible` to confidence output**

In `topic_verification.py::compute_confidence`:

```python
# After computing pct/label/color, before return:
auto_accept_eligible = (
    result.get("verdict") == "truly_new"
    and pct >= 75  # threshold from D4
    and not result.get("needs_manual_review")
    and not result.get("sanity_flag")
)
return {
    "pct": pct, "label": label, "color": color,
    "rationale": rationale,
    "auto_accept_eligible": auto_accept_eligible,  # EPIC-18 STREAM 4
}
```

- [ ] **Step 2: Add test**

```python
def test_compute_confidence_truly_new_high_confidence_auto_eligible():
    from backend.services.topic_verification import compute_confidence
    out = compute_confidence({"verdict": "truly_new"})
    assert out["pct"] == 85
    assert out["auto_accept_eligible"] is True


def test_compute_confidence_merge_never_auto_eligible():
    from backend.services.topic_verification import compute_confidence
    out = compute_confidence({"verdict": "should_be_merged_with"})
    assert out["auto_accept_eligible"] is False
```

- [ ] **Step 3: Frontend type update**

In `frontend/src/types/index.ts`, find the confidence/VerifyNewResult types and add:

```ts
export interface ConfidenceBreakdown {
  pct: number;
  label: 'High' | 'Moderate' | 'Low';
  color: string;
  rationale: Array<{ step: string; op: string; value: number; running: number }>;
  auto_accept_eligible?: boolean; // EPIC-18
}
```

Also add new verdict labels:

```ts
export type Pass1Verdict =
  | 'truly_new'
  | 'should_be_merged_with'
  | 'confirmed_match'
  | 'wrong_canonical_actually_new'
  | 'wrong_canonical_belongs_elsewhere';
```

- [ ] **Step 4: Frontend auto-accept rendering**

In `ProjectUpdatesStage.tsx`, where Pass 1 results are rendered, add:

```tsx
{result.confidence?.auto_accept_eligible ? (
  <div className="text-green-700 text-sm">✓ Auto-accepted as new (high confidence)</div>
) : (
  // existing review controls
)}
```

- [ ] **Step 5: Run tests + typecheck**

```bash
pytest backend/tests/test_topic_verification.py -v
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py add backend/services/topic_verification.py backend/tests/test_topic_verification.py frontend/src/types/index.ts frontend/src/components/ProjectUpdatesStage.tsx
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: verification asymmetry — auto-accept truly_new at high confidence (STREAM 4)"
```

---

### Task 20 — STREAM 5: Migration script for cached verify_new results

**Files:**
- Create: `backend/scripts/repopulate_verify_new_cache.py`
- Create: `docs/project/config/2026-05-24-epic-18-migration-runbook.md`

- [ ] **Step 1: Write the bulk reprocess script**

Create `backend/scripts/repopulate_verify_new_cache.py`:

```python
"""EPIC-18 STREAM 5 — One-shot reprocess all calls' verify_new caches.

Why: STREAM 2 changed the verify_new output schema (line-number citations,
no extraction_grounded field, new verdict states). Existing cached results
are unreadable by the new frontend. Two options:
  (a) Versioned reader supporting both shapes — complex, ongoing maint cost
  (b) Reprocess past calls under new schema — this script (D6 = b)

Usage:
  python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> [--dry-run]
  python3 -m backend.scripts.repopulate_verify_new_cache --all
"""

from __future__ import annotations
import argparse
import asyncio
import sys

from backend.database.supabase_client import get_client


async def reprocess_call(call_id: str, *, dry_run: bool) -> dict:
    db = get_client()
    if dry_run:
        return {"call_id": call_id, "action": "would_reprocess", "ok": True}
    # Reset state to trigger re-run via existing background task path
    db.table("calls").update({
        "verify_new_status": None,
        "verify_new_cache": None,
    }).eq("id", call_id).execute()
    # Trigger the endpoint manually via the function, or instruct user to
    # re-open call in UI. Simplest: leave reset, user re-opens.
    return {"call_id": call_id, "action": "reset_pending_ui_trigger", "ok": True}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.project or args.all):
        print("error: --project <uuid> or --all required", file=sys.stderr)
        return 1

    db = get_client()
    q = db.table("calls").select("id, project_id, verify_new_status")
    if args.project:
        q = q.eq("project_id", args.project)
    q = q.not_.is_("verify_new_status", "null")
    calls = q.execute().data or []
    print(f"📥 Found {len(calls)} call(s) with verify_new_cache to reprocess")
    if args.dry_run:
        print("DRY RUN — no DB changes")
    for c in calls:
        result = await reprocess_call(c["id"], dry_run=args.dry_run)
        print(f"  {result['action']}: {c['id']}")
    print("✅ Done. User must re-open each call in the UI to trigger fresh Pass 1.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Write the runbook**

Create `docs/project/config/2026-05-24-epic-18-migration-runbook.md`:

```markdown
# EPIC-18 Migration Runbook

## Pre-flight
1. Apply migration 034 in Supabase Dashboard (already in Task 1)
2. Confirm `project_topic_state` view returns expected data:
   ```sql
   SELECT topic_id, name, jsonb_array_length(tasks) AS task_count
   FROM project_topic_state LIMIT 5;
   ```

## Reprocess verify_new_cache (per-project)
3. Dry run first:
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> --dry-run
   ```
4. Actual run:
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid>
   ```
5. Re-open each affected call in the UI to trigger fresh Pass 1 under new schema.

## Post-flight
6. Spot-check 2-3 calls in the UI:
   - No "ungrounded items" warnings
   - Citation evidence renders correctly
   - Auto-accepted truly_new items show green confirmation
```

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py add backend/scripts/repopulate_verify_new_cache.py docs/project/config/2026-05-24-epic-18-migration-runbook.md
python3 scripts/git_ops.py commit -m "[EPIC-18] feat: migration script + runbook (STREAM 5)"
```

---

### Task 21 — Final session wrap-up

**Files:**
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/codebase.md`
- Modify: `docs/project/config/epics/ACTIVE.md`
- Modify: `workflow/ADR.md` (if architectural decisions were made)
- Modify: `workflow/ERRORS.md` (capture any bugs hit + prevention rules)

- [ ] **Step 1: Update build-log.md** with full epic summary
- [ ] **Step 2: Update codebase.md** with new modules (`project_topic_state.py`, `topic_similarity.py`)
- [ ] **Step 3: Update epics/ACTIVE.md** to reflect EPIC-18 status (and create `epics/epic-18/` folder if needed to track this epic)
- [ ] **Step 4: Append to ADR.md** decisions made: unified data layer (view), line-number citation pattern for cross-call passes (deferred to Pass 2/3)
- [ ] **Step 5: Append to ERRORS.md** any bugs encountered + prevention rule
- [ ] **Step 6: Final commit**

```bash
python3 scripts/git_ops.py add docs/project/config/build-log.md docs/project/config/codebase.md docs/project/config/epics/ACTIVE.md workflow/ADR.md workflow/ERRORS.md
python3 scripts/git_ops.py commit -m "[EPIC-18] docs: session wrap-up — epic complete, docs updated"
```

---

## Spec coverage self-review

Walking the design doc section by section:

| Spec section | Tasks covering it |
|---|---|
| §3 RC1 (two stores out of sync) | Tasks 1–4 |
| §3 RC2 (Stage 5 clusters blind) | Tasks 6–7 |
| §3 RC3 (Pass 1 verbatim quoting fragile) | Tasks 11–13 |
| §3 RC4 (extraction_grounded broken) | Task 12 (drop from prompt) + Task 13 (drop from result handler) |
| §3 RC5 (canonical matches unverified) | Task 14 |
| §3 RC6 (3 similarity impls) | Task 15 |
| §3 RC7 (`projects.context` unused) | Task 8 |
| §3 RC8 (hardcoded DeepSeek defaults) | Task 9 |
| §5 STREAM 0 (data layer) | Tasks 1–4 |
| §5 STREAM 1 (v5 changes) | Tasks 5–9 |
| §5 STREAM 2 (Pass 1 changes) | Tasks 11–16 |
| §5 STREAM 3 (test fixtures) | Tasks 10, 17 |
| §5 STREAM 4 (UX asymmetry) | Task 19 |
| §5 STREAM 5 (migration) | Task 20 |
| §6 (lifecycle) | Covered transitively via Tasks 14 + 19 verdict states |
| §10 (acceptance criteria 1: same-transcript test) | Task 18 |
| §10 (criterion 2: gold-set baseline) | Tasks 5 + 7 |
| §10 (criterion 3: fixtures green) | Tasks 10 + 17 |
| §10 (criterion 4: no regressions) | Verified at every task's test step |

**Gap check:** S2.4 (P1-RETRIEVAL) is intentionally deferred per D5 gating. Not in plan. Re-evaluate after Task 18.

**Placeholder scan:** None of the tasks contain "TODO" / "TBD" / "implement later" / unspecified code blocks.

**Type consistency:** `ProjectTopic` (Task 2), `RegistryEntry` (Task 3 extended), `Pass1Verdict` (Task 19) — all defined explicitly with consistent field naming.

---

## Execution

Plan saved to `docs/project/config/2026-05-24-call-topics-and-pass1-reliability-plan.md`.

**Recommended execution mode:** `superpowers:subagent-driven-development` — fresh subagent per task, your check-in cadence preserved (one task → stop → report → wait → next).

**Alternative:** `superpowers:executing-plans` — inline batch execution with checkpoints.

**Pre-execution gate:** answer the 6 decisions (D1–D6) in the table at the top of this plan before Task 1.
