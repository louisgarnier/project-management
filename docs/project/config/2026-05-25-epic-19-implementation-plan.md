# EPIC-19 — Task-Level Project Matching + Narrowed 3-Pass Synthesis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Check in with user after each task per project workflow (one task → stop → report → wait → next).

**Goal:** Replace topic-level project_matching with task-level N:M matching UI; narrow Pass 1/2 to safety-net roles; rewrite Pass 3 as synthesis-from-bound-tasks instead of full re-extraction.

**Architecture:** User does the identity decisions (manual task-level matching at project_matching stage). LLM only verifies (Pass 1: "really new?", Pass 2: "really not discussed?") and synthesizes (Pass 3: produce coherent merged topic state from confirmed bindings). The matching layer (which was broken in EPIC-18) becomes user-driven; the LLM stays in its lane (cognitive verification + summarization).

**Tech Stack:** Python 3.11+, FastAPI, Supabase Postgres, pytest, TypeScript/React/Next.js, AsyncOpenAI.

**Reference spec:** `docs/project/config/2026-05-25-epic-19-brainstorm.md`

**Commit prefix:** `[EPIC-19]`

---

## Pre-execution decisions (5 questions from spec Section 11, defaults locked)

| # | Decision | Default | Affects task |
|---|---|---|---|
| **Q1** | Pass 1 + Pass 2 execution | **Parallel** (different buckets, no overlap) | Task 11 |
| **Q2** | Pass 3 LLM call granularity | **Per-topic** (parallelizable across topics) | Task 9–10 |
| **Q3** | Cross-topic binding persistence | **Special match_group row type** with discriminator field `kind` | Task 1–3 |
| **Q4** | Pass 3 synthesis input format | **Structured JSON** (clear task identity) | Task 9 |
| **Q5** | Frontend matching UI interaction | **Keyboard-first** with click fallback | Task 12–13 |

If user wants to override any default, surface before Task 1.

---

## File map

### Phase 1 — Backend foundation
- **Create:** `backend/database/migrations/035_task_level_match_groups.sql` — schema extension
- **Create:** `backend/services/task_match_persistence.py` — task-level match group I/O
- **Create:** `backend/tests/test_task_match_persistence.py`
- **Modify:** `backend/services/topics_service.py:1101` — `save_match_groups` accepts task-level refs
- **Modify:** `backend/routers/topics.py:179` — endpoint passes task-level refs

### Phase 2 — Pass 1 narrowing
- **Modify:** `backend/services/topic_verification.py` — delete `check_citation_rarity` (lines 259-280 area), delete `run_verify_canonical_match` (lines 719+), delete sanity-flag penalty logic in `compute_confidence` (lines 363-368, 425)
- **Modify:** `backend/prompts/verify_new_topic.py` — delete `VERIFY_CANONICAL_MATCH_PROMPT` (line 161+), update main `VERIFY_NEW_TOPIC_PROMPT` for narrower scope
- **Modify:** `backend/tests/fixtures/pass1/wrong_canonical.json` — adapt (no longer canonical-match scenario; becomes a Pass 1 advisory case)
- **Modify:** `backend/tests/test_pass1_fixtures.py` — drop canonical-match test, adjust expectations

### Phase 3 — Pass 2 line-number migration
- **Modify:** `backend/prompts/verify_not_discussed.py` — line-number citation contract (drop free-form quote)
- **Modify:** `backend/services/topic_verification.py::run_verify_not_discussed` (lines ~783+) — use `verify_evidence_lines` from `citation_verify.py`, accept ingested transcript dict
- **Modify:** `backend/routers/topics.py` — Pass 2 background task ingests current transcript before passing in

### Phase 4 — Pass 3 synthesis rewrite
- **Modify:** `backend/prompts/extract_topic_updates.py` — replace re-extraction prompt body with synthesis prompt
- **Modify:** `backend/services/topic_verification.py::run_extract_topic_updates` — rename to `run_synthesize_merged_topic`; signature change (inputs: bound tasks + previous topic_updates row + transcripts); output: one new topic_updates row's content
- **Modify:** `backend/routers/topics.py` — Pass 3 background task assembles synthesis inputs

### Phase 5 — Frontend task-level matching
- **Create:** `frontend/src/components/TaskMatchingStage.tsx` — replaces topic-level matching
- **Create:** `frontend/src/components/TaskCard.tsx` — per-task display unit
- **Create:** `frontend/src/components/CrossTopicBindingModal.tsx` — modal when binding crosses topics
- **Modify:** `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — route project_matching stage to TaskMatchingStage
- **Modify:** `frontend/src/types/index.ts` — `TaskMatchGroup`, `BindingKind` (`'binding' | 'topic_merge'`)
- **Modify:** `frontend/src/api/client.ts` — `topicsAPI.saveTaskMatches` accepts task-level refs

### Phase 6 — Migration + smoke
- **Create:** `backend/scripts/migrate_match_groups_to_task_level.py` — backfill historical topic-level → task-level
- **Create:** `docs/project/config/2026-05-25-epic-19-migration-runbook.md` — manual steps
- **Modify:** `docs/project/config/build-log.md` — EPIC-19 wrap-up entry
- **Modify:** `docs/project/config/codebase.md` — module index additions
- **Modify:** `docs/project/config/epics/ACTIVE.md` — close out EPIC-19
- **Modify:** `workflow/ADR.md` — ADR-005 (task-level matching), ADR-006 (Pass 3 as synthesis not re-extraction)

---

## Tasks

### Task 1 — Phase 1: Migration 035 SQL (task-level match_groups schema)

**Files:**
- Create: `backend/database/migrations/035_task_level_match_groups.sql`

- [ ] **Step 1: Write migration SQL**

Create `backend/database/migrations/035_task_level_match_groups.sql`:

```sql
-- EPIC-19: task-level match groups
-- Extends topic_match_groups with task-level references.
-- Old call_topic_names + project_topic_ids retained for back-compat reads;
-- new task-level work uses call_task_refs + project_task_refs.

ALTER TABLE topic_match_groups
  ADD COLUMN IF NOT EXISTS call_task_refs JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS project_task_refs JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS kind TEXT DEFAULT 'binding'
    CHECK (kind IN ('binding', 'topic_merge'));

COMMENT ON COLUMN topic_match_groups.call_task_refs IS
'EPIC-19: list of {call_topic_name, task_id} referencing pending tasks from v5 output of this call';

COMMENT ON COLUMN topic_match_groups.project_task_refs IS
'EPIC-19: list of {project_topic_id, task_id} referencing existing tasks in project_topic_state';

COMMENT ON COLUMN topic_match_groups.kind IS
'EPIC-19: ''binding'' = task-to-task N:M match; ''topic_merge'' = explicit cross-topic merge decision';

-- Index for the common "fetch all groups for a call" query
CREATE INDEX IF NOT EXISTS idx_topic_match_groups_call_kind
  ON topic_match_groups(call_id, kind);
```

- [ ] **Step 2: DO NOT run the migration** — user runs it manually in Supabase Dashboard. Note in report.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: migration 035 — task-level match_groups schema extension"
```

---

### Task 2 — Phase 1: task_match_persistence service module

**Files:**
- Create: `backend/services/task_match_persistence.py`
- Test: `backend/tests/test_task_match_persistence.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_task_match_persistence.py`:

```python
"""EPIC-19 — Tests for task-level match group persistence."""
from unittest.mock import MagicMock
from backend.services.task_match_persistence import (
    save_task_match_groups, load_task_match_groups, TaskMatchGroup,
)


def _fake_db():
    db = MagicMock()
    return db


def test_save_task_match_groups_persists_n_to_m_binding():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="binding",
            call_task_refs=[{"call_topic_name": "ARM", "task_id": "t1"}, {"call_topic_name": "ARM", "task_id": "t2"}],
            project_task_refs=[{"project_topic_id": "p-arm", "task_id": "pt1"}],
        )
    ]
    result = save_task_match_groups(call_id="c-1", groups=groups, db=db)
    assert result["saved"] == 1
    db.table.assert_any_call("topic_match_groups")
    insert_call = db.table.return_value.insert.call_args
    inserted = insert_call.args[0]
    assert inserted["kind"] == "binding"
    assert len(inserted["call_task_refs"]) == 2
    assert len(inserted["project_task_refs"]) == 1


def test_save_task_match_groups_deletes_previous_groups_first():
    db = _fake_db()
    save_task_match_groups(call_id="c-1", groups=[], db=db)
    db.table.return_value.delete.return_value.eq.assert_called_with("call_id", "c-1")


def test_save_task_match_groups_topic_merge_kind():
    db = _fake_db()
    groups = [
        TaskMatchGroup(
            kind="topic_merge",
            call_task_refs=[],
            project_task_refs=[{"project_topic_id": "p-a"}, {"project_topic_id": "p-b"}],
        )
    ]
    save_task_match_groups(call_id="c-1", groups=groups, db=db)
    inserted = db.table.return_value.insert.call_args.args[0]
    assert inserted["kind"] == "topic_merge"
```

- [ ] **Step 2: Run test (expect failure)**

```bash
cd "/Users/louisgarnier/Claude/Project management"
pytest backend/tests/test_task_match_persistence.py -v
```

Expected: ImportError / ModuleNotFoundError.

- [ ] **Step 3: Implement the service**

Create `backend/services/task_match_persistence.py`:

```python
"""EPIC-19 — Task-level match group persistence.

Replaces the topic-level save_match_groups for EPIC-19 task-level matching.
Old topic-level path retained in topics_service.save_match_groups for
back-compat reads of historical projects.
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from backend.database.supabase_client import get_client

logger = logging.getLogger("calltracker.task_match_persistence")


class TaskRef(TypedDict, total=False):
    call_topic_name: str       # for call_task_refs
    project_topic_id: str      # for project_task_refs
    task_id: str               # the task UUID (v5-stamped for call refs, persistent for project refs)


class TaskMatchGroup(TypedDict):
    kind: Literal["binding", "topic_merge"]
    call_task_refs: list[TaskRef]
    project_task_refs: list[TaskRef]


def save_task_match_groups(
    call_id: str, groups: list[TaskMatchGroup], *, db=None,
) -> dict:
    """Persist task-level match groups. Idempotent (delete-then-insert)."""
    client = db if db is not None else get_client()
    client.table("topic_match_groups").delete().eq("call_id", call_id).execute()
    for g in groups:
        client.table("topic_match_groups").insert({
            "call_id": call_id,
            "kind": g.get("kind", "binding"),
            "call_task_refs": g.get("call_task_refs", []),
            "project_task_refs": g.get("project_task_refs", []),
            # Legacy cols populated for back-compat reads
            "call_topic_names": sorted({r.get("call_topic_name", "").lower().strip()
                                        for r in g.get("call_task_refs", [])
                                        if r.get("call_topic_name")}),
            "project_topic_ids": sorted({r.get("project_topic_id")
                                         for r in g.get("project_task_refs", [])
                                         if r.get("project_topic_id")}),
        }).execute()
    logger.info(f"🗄️ [TaskMatch] saved {len(groups)} group(s) for call {call_id}")
    return {"saved": len(groups)}


def load_task_match_groups(call_id: str, *, db=None) -> list[TaskMatchGroup]:
    """Return all task-level match groups for a call."""
    client = db if db is not None else get_client()
    rows = (
        client.table("topic_match_groups")
        .select("kind, call_task_refs, project_task_refs")
        .eq("call_id", call_id)
        .execute()
        .data
    ) or []
    return [
        TaskMatchGroup(
            kind=r.get("kind") or "binding",
            call_task_refs=r.get("call_task_refs") or [],
            project_task_refs=r.get("project_task_refs") or [],
        )
        for r in rows
    ]
```

- [ ] **Step 4: Run tests**

```bash
pytest backend/tests/test_task_match_persistence.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: task_match_persistence service for task-level match groups"
```

---

### Task 3 — Phase 1: save_match_groups endpoint accepts task-level refs

**Files:**
- Modify: `backend/services/topics_service.py:1101-1127` (`save_match_groups`)
- Modify: `backend/routers/topics.py:179-196` (endpoint signature)
- Test: extend `backend/tests/test_topics.py`

- [ ] **Step 1: Add failing test**

Append to `backend/tests/test_topics.py`:

```python
def test_save_match_groups_persists_task_level_refs(monkeypatch):
    """EPIC-19: endpoint accepts task-level match groups via save_task_match_groups."""
    from backend.services.topics_service import save_match_groups
    import asyncio
    saved = []
    async def fake_save(call_id, groups, db=None):
        saved.append({"call_id": call_id, "groups": groups})
        return {"saved": len(groups)}
    monkeypatch.setattr(
        "backend.services.topics_service.save_task_match_groups",
        fake_save,
    )
    # Stub the kanban_stage advance
    monkeypatch.setattr(
        "backend.services.topics_service.get_client",
        lambda: type("F", (), {
            "table": lambda self, *a, **kw: type("Q", (), {
                "update": lambda self, *a, **kw: self,
                "eq": lambda self, *a, **kw: self,
                "execute": lambda self: type("R", (), {"data": []})(),
            })()
        })(),
    )
    out = asyncio.run(save_match_groups(
        "c-1",
        [{"kind": "binding",
          "call_task_refs": [{"call_topic_name": "ARM", "task_id": "t1"}],
          "project_task_refs": [{"project_topic_id": "p-arm", "task_id": "pt1"}]}],
    ))
    assert out["saved"] == 1
    assert saved[0]["groups"][0]["kind"] == "binding"
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest backend/tests/test_topics.py::test_save_match_groups_persists_task_level_refs -v
```

Expected: FAIL — current `save_match_groups` doesn't accept task-level shape.

- [ ] **Step 3: Refactor save_match_groups in topics_service.py**

Replace `save_match_groups` body at `backend/services/topics_service.py:1101-1127`:

```python
async def save_match_groups(call_id: str, groups: list[dict]) -> dict:
    """EPIC-19: task-level match groups.

    Each group: {
      kind: "binding" | "topic_merge",
      call_task_refs: [{call_topic_name, task_id}, ...],
      project_task_refs: [{project_topic_id, task_id}, ...],
    }
    """
    from backend.services.task_match_persistence import save_task_match_groups
    db = get_client()
    result = save_task_match_groups(call_id, groups, db=db)
    db.table("calls").update({"kanban_stage": "project_updates"}).eq("id", call_id).execute()
    logger.info(f"✅ [Topics] Saved {result['saved']} task-level match group(s) → project_updates")
    return result
```

- [ ] **Step 4: Update router signature**

In `backend/routers/topics.py:179-196`, update the Pydantic model used by `/save-matches`:

```python
class TaskRefIn(PydanticBaseModel):
    call_topic_name: str | None = None
    project_topic_id: str | None = None
    task_id: str | None = None

class TaskMatchGroupIn(PydanticBaseModel):
    kind: Literal["binding", "topic_merge"] = "binding"
    call_task_refs: list[TaskRefIn] = []
    project_task_refs: list[TaskRefIn] = []

@router.post("/calls/{call_id}/topics/save-matches", status_code=200)
async def save_matches(call_id: str, groups: list[TaskMatchGroupIn]):
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        return result
    except Exception as e:
        logger.exception(f"❌ [Topics] save_matches failed for call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

(Add `from typing import Literal` + `from pydantic import BaseModel as PydanticBaseModel` if not already imported.)

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topics.py backend/tests/test_task_match_persistence.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] refactor: save_match_groups endpoint accepts task-level refs (Phase 1 done)"
```

---

### Task 4 — Phase 2: Delete S2.2 P1-BIDIRECTIONAL path (verify_canonical_match)

**Files:**
- Modify: `backend/services/topic_verification.py` (remove `run_verify_canonical_match` function and imports)
- Modify: `backend/prompts/verify_new_topic.py` (remove `VERIFY_CANONICAL_MATCH_PROMPT`)
- Modify: `backend/routers/topics.py` (remove canonical-candidates branch in `_run_verify_new_background`)
- Modify: `backend/tests/test_topic_verification.py` (delete 3 `run_verify_canonical_match` tests)

- [ ] **Step 1: Find and delete `run_verify_canonical_match` function**

In `backend/services/topic_verification.py`:
- Delete the entire `async def run_verify_canonical_match(...)` function starting at line ~719
- Delete any imports it brings in that aren't used elsewhere

- [ ] **Step 2: Delete `VERIFY_CANONICAL_MATCH_PROMPT` constant**

In `backend/prompts/verify_new_topic.py:161+`, delete the entire `VERIFY_CANONICAL_MATCH_PROMPT` constant block.

- [ ] **Step 3: Delete canonical-candidates branch in router**

In `backend/routers/topics.py::_run_verify_new_background`, find the loop that runs `run_verify_canonical_match` (per EPIC-18 Task 14's implementation — it iterates `canonical_candidates`). Delete the entire loop. The router now only handles `new_candidates` (verify-new).

If the router builds both `new_candidates` AND `canonical_candidates` from `topic_match_groups`, simplify: under EPIC-19, candidate tasks that went into `merged_topics` are processed by Pass 3 directly — not Pass 1. So `_run_verify_new_background` only runs on candidate topics in the `new_topics` bucket.

The bucket determination logic should now read from `topic_match_groups` using the new task-level shape:
- `new_topics` bucket = candidate topic names whose tasks have no `project_task_refs` in any match group
- `old_untouched_topics` bucket = project topics whose tasks aren't referenced in any group's `project_task_refs`
- `merged_topics` bucket = the rest

Add a helper at the top of `_run_verify_new_background`:

```python
from backend.services.task_match_persistence import load_task_match_groups
groups = load_task_match_groups(call_id, db=db)

# Bucket assignment
bound_project_task_ids = set()
bound_call_topic_names = set()
for g in groups:
    if g["kind"] != "binding":
        continue
    for r in g["project_task_refs"]:
        if r.get("task_id"):
            bound_project_task_ids.add(r["task_id"])
    for r in g["call_task_refs"]:
        if r.get("call_topic_name"):
            bound_call_topic_names.add(r["call_topic_name"].lower())

# new_candidates = candidate topics whose names aren't in bound_call_topic_names
# (existing pending_topics list already loaded earlier in the function)
new_candidates = [
    t for t in pending_topics
    if (t.get("name") or "").lower() not in bound_call_topic_names
]
```

- [ ] **Step 4: Delete obsolete tests**

In `backend/tests/test_topic_verification.py`, delete the 3 tests added for `run_verify_canonical_match` in EPIC-18 Task 14:
- `test_run_verify_canonical_match_confirmed`
- `test_run_verify_canonical_match_wrong_canonical`
- `test_run_verify_canonical_match_failed_citations`

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topic_verification.py backend/tests/test_topics.py backend/tests/test_pass1_fixtures.py -v
```

Expected: PASS (no more references to canonical_match).

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] refactor: delete S2.2 canonical-match path (never triggered in prod; replaced by manual task matching)"
```

---

### Task 5 — Phase 2: Delete rarity check + sanity flag penalty stack

**Files:**
- Modify: `backend/services/topic_verification.py`
- Modify: `backend/tests/test_topic_verification.py`

- [ ] **Step 1: Delete `check_citation_rarity` function**

In `backend/services/topic_verification.py` around line 259, delete the entire `def check_citation_rarity(...)` function.

- [ ] **Step 2: Delete the rarity-check call in run_verify_new**

Around line 645 in `run_verify_new`, find and delete:

```python
# (b) Citation rarity check (each verdict citation must contain a rare candidate term)
if not final.get("needs_manual_review") and precheck:
    idf = precheck.get("_idf_for_rarity_check") or {}
    rarity_fails = check_citation_rarity(verdict_cits, candidate, idf)
    if rarity_fails:
        final["needs_manual_review"] = True
        final["sanity_flag"] = "citations_lack_rare_terms"
        final.setdefault("failed_citations", []).extend(rarity_fails)
        await _log(...)
```

- [ ] **Step 3: Delete the sanity-flag penalty step in compute_confidence**

In `compute_confidence` (lines 363-368), delete:

```python
sanity_flag = result.get("sanity_flag")
if sanity_flag:
    running -= 15
    rationale.append({
        "step": f"Sanity flag: {sanity_flag}",
        "op": "− penalty",
        "value": 15,
        "running": round(running, 1),
    })
```

- [ ] **Step 4: Remove sanity_flag from auto_accept_eligible check**

In `compute_confidence` (line 425 area), change:

```python
auto_accept_eligible = (
    result.get("verdict") == "truly_new"
    and pct >= 75
    and not result.get("needs_manual_review")
    and not result.get("sanity_flag")  # ← DELETE THIS LINE
)
```

- [ ] **Step 5: Delete sanity flag setters that remain**

Search remaining file for `sanity_flag` references. Around lines 637, 649, 665, 675, 678, 712 — delete the lines that SET `final["sanity_flag"]` (the rest of the surrounding logic also needs to be deleted along with the rarity-check, ≥2-citation, reasoning-anchor checks).

Specifically, the post-LLM defense-in-depth block in run_verify_new (~lines 625-680) had 4 checks:
- (a) ≥2 citations for merge — KEEP this one (it's a legitimate evidence count check)
- (b) Rarity check — DELETE
- (c) Reasoning references both sides' tasks — DELETE (with check_reasoning_references_tasks function)
- (d) sanity_check_llm_vs_lexical — KEEP but stop setting sanity_flag (just log)

Actually simpler: delete the whole defense-in-depth block (b)+(c)+(d) and keep only the citation-count check (a).

Replace the block (lines roughly 625-680, after `# ── Post-LLM mechanical defense-in-depth ──` comment) with:

```python
# EPIC-19: simplified post-LLM check.
# Only the ≥2 verdict-citation count check is retained.
# Rarity + reasoning-anchor + sanity-flag stack removed (was producing
# false-positive penalties on topics with common/code-like terms; see EPIC-19
# spec Section 1).
if final.get("verdict") == "should_be_merged_with":
    verdict_cits = [c for c in cits if (c.get("for") or "verdict") == "verdict"]
    if len(verdict_cits) < 2:
        final["needs_manual_review"] = True
        final.setdefault("failed_citations", []).append(
            f"merge verdict requires ≥2 verdict citations, got {len(verdict_cits)}"
        )
        await _log(f"      [{name}] ⚠ merge has {len(verdict_cits)} verdict citation(s) (need ≥2) — needs review")
```

- [ ] **Step 6: Delete `check_reasoning_references_tasks` function**

If still present, delete it from topic_verification.py.

- [ ] **Step 7: Update tests that asserted sanity_flag behavior**

In `backend/tests/test_topic_verification.py`:
- Delete `test_compute_confidence_truly_new_with_sanity_flag_not_eligible`
- Adjust any other test that referenced `sanity_flag` or `check_citation_rarity`

- [ ] **Step 8: Run tests**

```bash
pytest backend/tests/test_topic_verification.py backend/tests/test_pass1_fixtures.py backend/tests/test_topics.py -v
```

Expected: PASS. Note: Pass 1 fixture tests should still work — the verdict logic is unchanged; only the penalty stack went away. Confidence numbers will be HIGHER (closer to base 85 for merge verdicts).

- [ ] **Step 9: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] refactor: delete rarity check + sanity flag penalty stack (Pass 1 confidence reflects actual match quality)"
```

---

### Task 6 — Phase 2: Update Pass 1 prompt for narrower scope

**Files:**
- Modify: `backend/prompts/verify_new_topic.py`

- [ ] **Step 1: Soften the Pass 1 prompt's framing**

Pass 1 is now a safety-net for the user's "this is new" decision. The prompt should reflect:
- The user has already manually decided this candidate doesn't bind to any existing task
- Pass 1's job: re-verify, suggest if user missed something
- Bias: default to confirming user's decision; only flag if there's strong evidence of a missed match

In `backend/prompts/verify_new_topic.py::VERIFY_NEW_TOPIC_PROMPT`, replace the ROLE + DEFINITION section with:

```
ROLE: You are a PMO safety-net verifier. The user has manually reviewed
candidate tasks and decided this candidate topic is genuinely new (no tasks
bound to any existing project topic). Your job: re-verify this decision
against past transcripts and existing project topics, and SUGGEST a merge
ONLY if there is strong evidence the user missed a continuation of work.

Default to confirming the user's "truly_new" decision. Flag a merge
suggestion only when the candidate task list demonstrably continues a
specific existing task's work.

──────────────────────────────────────────────────────────────────────
DEFINITION OF "USER LIKELY MISSED A MERGE"
──────────────────────────────────────────────────────────────────────
The candidate's task(s) describe the same concrete work as an existing
project task: same problem, same deliverable, same domain. Not just
shared platform/vendor name. Not just shared timeframe.
```

Keep the existing PROCESS, CITATION CONTRACT, and OUTPUT FORMAT sections (with `confirmed_new` and `suggest_merge_with` verdicts).

- [ ] **Step 2: Update output schema in the prompt**

Replace the OUTPUT FORMAT block's `final_verdict` and `verdict` values to be the simplified set:

```
{
  "evaluations": [...],
  "verdict": "confirmed_new" | "suggest_merge_with",
  "matched_topic_id": "<uuid or null>",
  "matched_topic_name": "<string or null>",
  "merge_reasoning": "<one sentence if suggest_merge_with, else 'No existing topic continues the candidate's work'>",
  "citations": [
    {"call_id": "<uuid>", "evidence_lines": [<start>, <end>], "for": "verdict"}
  ]
}
```

Remove old verdicts: `truly_new` and `should_be_merged_with` are renamed. (The orchestration code in `run_verify_new` accepts either; we'll align in Task 7.)

- [ ] **Step 3: Append EPIC-19 changelog note to top docstring**

After existing docstring lines in `verify_new_topic.py`:

```python
"""... existing docstring ...

EPIC-19 (2026-05-25): Pass 1 reframed as safety-net verification of user's
manual matching decision. Verdicts simplified to confirmed_new /
suggest_merge_with. Default bias toward confirming user's decision.
"""
```

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: Pass 1 prompt — safety-net framing (user already matched manually)"
```

---

### Task 7 — Phase 2: Align run_verify_new + fixtures with new verdict names

**Files:**
- Modify: `backend/services/topic_verification.py::run_verify_new`
- Modify: `backend/tests/fixtures/pass1/*.json`
- Modify: `backend/tests/test_pass1_fixtures.py`

- [ ] **Step 1: Add verdict name normalization in run_verify_new**

In `run_verify_new`, after parsing the LLM response, add:

```python
# EPIC-19: normalize verdict names (prompt uses confirmed_new / suggest_merge_with;
# legacy callers may still expect truly_new / should_be_merged_with).
v = result.get("verdict")
if v == "confirmed_new":
    result["verdict"] = "truly_new"  # legacy alias
elif v == "suggest_merge_with":
    result["verdict"] = "should_be_merged_with"  # legacy alias
result["final_verdict"] = result["verdict"]
```

This bridges the new prompt vocabulary with existing downstream code.

- [ ] **Step 2: Update fixtures for new framing**

In each `backend/tests/fixtures/pass1/*.json`, the `expected_verdict.verdict` may still use the legacy names (`truly_new`, `should_be_merged_with`) — that's fine, the normalization step above handles both.

For `wrong_canonical.json`: this fixture was for the deleted canonical-match path. Repurpose it as a Pass 1 advisory case (or delete it).

Recommended: delete `wrong_canonical.json` and the `test_fixture_wrong_canonical` test (the scenario it represented is now handled by the user's manual matching decision, not Pass 1).

```bash
rm backend/tests/fixtures/pass1/wrong_canonical.json
```

In `backend/tests/test_pass1_fixtures.py`, delete the `test_fixture_wrong_canonical` test function.

- [ ] **Step 3: Run tests**

```bash
pytest backend/tests/test_pass1_fixtures.py backend/tests/test_topic_verification.py -v
```

Expected: PASS (4 fixtures × scenario tests + topic_verification tests).

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] refactor: Pass 1 verdict vocabulary aligned; drop wrong_canonical fixture (Phase 2 complete)"
```

---

### Task 8 — Phase 3: Pass 2 line-number citation migration

**Files:**
- Modify: `backend/prompts/verify_not_discussed.py`
- Modify: `backend/services/topic_verification.py::run_verify_not_discussed`
- Modify: `backend/routers/topics.py` (Pass 2 background task)
- Test: extend `backend/tests/test_topic_verification.py`

- [ ] **Step 1: Update Pass 2 prompt to line-number contract**

Replace `backend/prompts/verify_not_discussed.py` content:

```python
"""Pass ② — verify_not_discussed prompt body.

EPIC-19 (2026-05-25): citation contract switched to line-numbers (matches
v5 Stage 4 + EPIC-18 ADR-004 pattern). Replaces free-form quote citations.
Pass 2 is now a narrowed safety-net: for topics the user marked as
'not touched this call' in manual matching, verify against the current
call's transcript that no tasks from this topic were actually mentioned.
"""

VERIFY_NOT_DISCUSSED_PROMPT: str = """\
ROLE: You are a PMO safety-net verifier. The user has manually decided
this existing project topic was NOT touched in the current call. Your job:
re-verify by scanning the current call's transcript (line-numbered) for
any mention of the topic's tasks.

Default to confirming the user's "not_discussed" decision. Flag a missed
discussion ONLY if you find a specific transcript passage that clearly
discusses one of the topic's tasks.

CITATION CONTRACT (line-numbers, anti-hallucination):
The transcript is line-numbered (format: "0001  <text>"). DO NOT copy
quotes. Cite by line range:

  {"call_id": "<uuid>", "evidence_lines": [start_line, end_line]}

OUTPUT (strict JSON):
{
  "verdict": "confirmed_not_discussed" | "suggest_discussed_at",
  "reasoning": "<one sentence>",
  "citation": {"call_id": "<uuid>", "evidence_lines": [<start>, <end>]} | null
}

REMEMBER: default to confirmed_not_discussed.
"""
```

- [ ] **Step 2: Update `run_verify_not_discussed` to use line-range verifier**

In `backend/services/topic_verification.py::run_verify_not_discussed` (~line 783), change signature and verifier:

```python
async def run_verify_not_discussed(
    topic: dict, ingested_transcript: dict, *,
    call_id: str, llm: str, model: str | None, log_fn=None,
) -> dict:
    """EPIC-19: Pass 2 — verify a topic wasn't discussed in the supplied transcript.

    Args:
        ingested_transcript: v5 Stage 0 ingest output dict {line_count, lines}.
    """
    from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT
    from backend.services.citation_verify import verify_evidence_lines

    name = topic.get("name", "?")
    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    transcript_block = (
        f"--- CALL {call_id} ({ingested_transcript['line_count']} lines) ---\n"
        + "\n".join(f"{ln['idx']}  {ln['text']}" for ln in ingested_transcript.get("lines", []))
    )
    anchor = json.dumps({
        "topic_name": topic.get("name"),
        "tasks": [{"task": t.get("task"), "next_step": t.get("next_step"),
                   "key_terms": t.get("key_terms", [])}
                  for t in (topic.get("tasks") or [])],
    }, indent=2)
    prompt = (
        f"{VERIFY_NOT_DISCUSSED_PROMPT}\n\n"
        f"TOPIC ANCHOR (existing project topic, from previous call's project_updates):\n{anchor}\n\n"
        f"CURRENT CALL TRANSCRIPT (line-numbered):\n{transcript_block}"
    )
    await _log(f"      [{name}] asking LLM to scan current call for any mention")
    result = await _call_llm(prompt, llm, model=model)
    if not isinstance(result, dict):
        return {"verdict": "confirmed_not_discussed", "needs_manual_review": True,
                "reasoning": "LLM non-dict response — defaulting to user's decision",
                "citation": None}
    cit = result.get("citation")
    cits = [cit] if cit else []
    ok, failures = verify_evidence_lines(cits, {call_id: ingested_transcript})
    result["needs_manual_review"] = not ok
    if not ok:
        result["failed_citations"] = failures
    return result
```

- [ ] **Step 3: Update router to ingest current transcript before Pass 2**

In `backend/routers/topics.py`, find the Pass 2 background task (`_run_verify_not_discussed_background` or similar). Update transcript loading:

```python
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript

current_row = db.table("calls").select("transcript").eq("id", call_id).execute().data
current_transcript_raw = (current_row[0] or {}).get("transcript") or ""
ingested = ingest_transcript(current_transcript_raw)

# ... existing topic loop ...
r = await run_verify_not_discussed(
    topic=t, ingested_transcript=ingested,
    call_id=call_id, llm=llm, model=model, log_fn=plog.log,
)
```

- [ ] **Step 4: Add test for new Pass 2**

In `backend/tests/test_topic_verification.py`:

```python
@pytest.mark.asyncio
async def test_run_verify_not_discussed_uses_line_range(monkeypatch):
    """EPIC-19: Pass 2 cites by line range, verified via bounds check."""
    from backend.services.topic_verification import run_verify_not_discussed
    async def fake_llm(*a, **kw):
        return {
            "verdict": "confirmed_not_discussed",
            "reasoning": "topic not mentioned in current call",
            "citation": None,
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    ingested = {"line_count": 3, "lines": [
        {"idx": "0001", "text": "Hello"},
        {"idx": "0002", "text": "World"},
        {"idx": "0003", "text": "!"},
    ]}
    out = await run_verify_not_discussed(
        topic={"name": "ARM", "tasks": []},
        ingested_transcript=ingested,
        call_id="c-1", llm="x", model="y",
    )
    assert out["verdict"] == "confirmed_not_discussed"
    assert out["needs_manual_review"] is False
```

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topic_verification.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: Pass 2 uses line-number citations + safety-net framing (Phase 3 complete)"
```

---

### Task 9 — Phase 4: Pass 3 synthesis prompt rewrite

**Files:**
- Modify: `backend/prompts/extract_topic_updates.py`

- [ ] **Step 1: Replace the prompt body with synthesis framing**

Replace `backend/prompts/extract_topic_updates.py` content:

```python
"""Pass ③ — task-merge synthesis prompt body.

EPIC-19 (2026-05-25): rewritten from full re-extraction to task-merge
synthesis. Inputs: previously-bound tasks from match groups + previous
topic_updates state + transcripts. Output: one coherent updated topic
snapshot per merged topic, with all task identities preserved.
"""

EXTRACT_TOPIC_UPDATES_PROMPT: str = """\
ROLE: You are a PMO synthesis engine. The user has manually matched tasks
across calls (project_matching stage) and verified via Pass 1 + Pass 2.
For one topic, you receive:
  - The previous call's project_updates state for this topic (accumulated
    chronological state with task history)
  - New candidate tasks from the current call that the user has bound to
    this topic (via match_groups OR Pass 1/2 user override)
  - Past transcripts (line-numbered)
  - Current call's transcript (line-numbered)

Your job: produce ONE coherent updated topic snapshot that merges the new
bindings into the existing task list. Preserve task identity (task_id stays
stable across updates). Update next_step / status / key_terms / open_questions /
decisions where the new call adds information. Generate a topic-level summary
that captures the topic's current state across all calls.

DO NOT:
- Re-extract tasks from transcripts (the bindings are already determined)
- Invent new tasks not present in the inputs
- Re-merge or split tasks beyond what the bindings indicate

DO:
- Update each task's next_step + status to reflect the latest call's evidence
- Append new open_questions or decisions raised in the current call
- Add citations for any updates (line-range format)
- Set topic-level status rollup: open > in_progress > resolved

CITATION CONTRACT (line-numbers, anti-hallucination):
Each transcript is line-numbered. DO NOT copy quotes. Cite by:

  {"call_id": "<uuid>", "evidence_lines": [start_line, end_line]}

OUTPUT (strict JSON):
{
  "topic_name": "<existing topic name>",
  "summary": "<2-4 sentences synthesizing the topic state across calls>",
  "status": "open" | "in_progress" | "resolved",
  "tasks": [
    {
      "task_id": "<stable UUID>",
      "task": "<task description>",
      "next_step": "<latest next action>",
      "owner": "<owner name>",
      "status": "open" | "in_progress" | "resolved",
      "key_terms": [...],
      "open_questions": [...],
      "decisions": [...],
      "primary_citation": {"call_id": "<uuid>", "evidence_lines": [...]},
      "supporting_citations": [...]
    }, ...
  ],
  "evidence_trail": [
    {"call_id": "<uuid>", "evidence_lines": [...], "action_label": "task added | next step added | status change | ..."},
    ...
  ]
}
"""
```

- [ ] **Step 2: Commit (no tests yet — orchestration code comes in Task 10)**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: Pass 3 prompt — synthesis from bound tasks (no re-extraction)"
```

---

### Task 10 — Phase 4: Pass 3 orchestration (run_synthesize_merged_topic)

**Files:**
- Modify: `backend/services/topic_verification.py` (replace `run_extract_topic_updates` with `run_synthesize_merged_topic`)
- Modify: `backend/routers/topics.py` (Pass 3 background task)
- Test: extend `backend/tests/test_topic_verification.py`

- [ ] **Step 1: Write failing test**

In `backend/tests/test_topic_verification.py`:

```python
@pytest.mark.asyncio
async def test_run_synthesize_merged_topic_returns_snapshot(monkeypatch):
    """EPIC-19: Pass 3 synthesizes one topic from bound tasks + history."""
    from backend.services.topic_verification import run_synthesize_merged_topic
    async def fake_llm(*a, **kw):
        return {
            "topic_name": "ARM",
            "summary": "Account aggregation risk modeling continuing work.",
            "status": "in_progress",
            "tasks": [
                {"task_id": "pt-1", "task": "Investigate Monte Carlo memory issue",
                 "next_step": "Run profiler on the failing job",
                 "owner": "Mark", "status": "in_progress",
                 "key_terms": ["Monte Carlo", "memory"],
                 "open_questions": [], "decisions": [],
                 "primary_citation": {"call_id": "c-2", "evidence_lines": [10, 15]},
                 "supporting_citations": []}
            ],
            "evidence_trail": [
                {"call_id": "c-1", "evidence_lines": [5, 8], "action_label": "task added"},
                {"call_id": "c-2", "evidence_lines": [10, 15], "action_label": "next step added"},
            ],
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_synthesize_merged_topic(
        topic_name="ARM",
        previous_update={"tasks": [{"task_id": "pt-1", "task": "Investigate Monte Carlo memory issue"}]},
        new_bound_tasks=[{"task_id": "ct-1", "task": "Run profiler on failing job"}],
        ingested_transcripts={
            "c-1": {"line_count": 20, "lines": [{"idx": f"{i:04d}", "text": f"line {i}"} for i in range(1, 21)]},
            "c-2": {"line_count": 20, "lines": [{"idx": f"{i:04d}", "text": f"line {i}"} for i in range(1, 21)]},
        },
        llm="x", model="y",
    )
    assert out["topic_name"] == "ARM"
    assert out["status"] == "in_progress"
    assert len(out["tasks"]) == 1
    assert out["tasks"][0]["task_id"] == "pt-1"
    assert out["needs_manual_review"] is False
```

- [ ] **Step 2: Run test (expect failure)**

```bash
pytest backend/tests/test_topic_verification.py::test_run_synthesize_merged_topic_returns_snapshot -v
```

Expected: AttributeError — function not defined.

- [ ] **Step 3: Implement run_synthesize_merged_topic**

In `backend/services/topic_verification.py`, find the existing `async def run_extract_topic_updates(...)` and replace its body. Rename to `run_synthesize_merged_topic`:

```python
async def run_synthesize_merged_topic(
    topic_name: str,
    previous_update: dict,
    new_bound_tasks: list[dict],
    ingested_transcripts: dict[str, dict],
    *,
    llm: str,
    model: str | None,
    log_fn=None,
) -> dict:
    """EPIC-19: Pass 3 — synthesize one merged topic's updated state.

    Args:
        topic_name: the existing project topic's name (anchor)
        previous_update: the topic's last topic_updates row (full state)
        new_bound_tasks: candidate tasks from this call that bound to this topic
        ingested_transcripts: {call_id: ingest_dict} for past + current calls

    Returns the synthesized topic snapshot dict + needs_manual_review flag.
    """
    from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT
    from backend.services.citation_verify import verify_evidence_lines

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ({ing['line_count']} lines) ---\n"
        + "\n".join(f"{ln['idx']}  {ln['text']}" for ln in ing.get("lines", []))
        for cid, ing in ingested_transcripts.items()
    )
    inputs = {
        "topic_name": topic_name,
        "previous_update_state": previous_update,
        "new_bound_tasks_this_call": new_bound_tasks,
    }
    prompt = (
        f"{EXTRACT_TOPIC_UPDATES_PROMPT}\n\n"
        f"INPUTS (structured JSON):\n{json.dumps(inputs, indent=2)}\n\n"
        f"TRANSCRIPTS (line-numbered, chronological):\n{transcripts_block}"
    )
    await _log(f"      [{topic_name}] synthesizing merged update from {len(new_bound_tasks)} new task(s) + previous state")
    result = await _call_llm(prompt, llm, model=model)
    if not isinstance(result, dict):
        return {"topic_name": topic_name, "tasks": [], "summary": "",
                "status": "open", "evidence_trail": [],
                "needs_manual_review": True,
                "failed_citations": ["LLM returned non-dict response"]}

    # Collect all citations for verification
    all_cits = []
    for t in result.get("tasks") or []:
        if t.get("primary_citation"):
            all_cits.append(t["primary_citation"])
        all_cits.extend(t.get("supporting_citations") or [])
    for e in result.get("evidence_trail") or []:
        if e.get("evidence_lines") and e.get("call_id"):
            all_cits.append({"call_id": e["call_id"], "evidence_lines": e["evidence_lines"]})

    ok, failures = verify_evidence_lines(all_cits, ingested_transcripts)
    result["needs_manual_review"] = not ok
    if not ok:
        result["failed_citations"] = failures
        await _log(f"      [{topic_name}] {len(failures)} citation(s) failed bounds check — flagged for review")
    else:
        await _log(f"      [{topic_name}] ✓ all {len(all_cits)} citation(s) verified")
    return result
```

- [ ] **Step 4: Update router Pass 3 background task**

In `backend/routers/topics.py`, find the existing Pass 3 background task (extract_updates). Rewrite to assemble synthesis inputs per topic:

Sketch:

```python
async def _run_synthesize_background(call_id: str) -> None:
    """EPIC-19 Pass 3 — synthesize merged topic states from bound tasks."""
    from backend.services.task_match_persistence import load_task_match_groups
    from backend.services.topic_verification import run_synthesize_merged_topic
    from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript

    db = get_client()
    plog = ProgressLogger(db, call_id, "extract_updates_cache")
    await plog.start()

    try:
        # Load all match groups for this call
        groups = load_task_match_groups(call_id, db=db)
        binding_groups = [g for g in groups if g["kind"] == "binding" and g["project_task_refs"]]
        # Each unique project_topic_id from project_task_refs is a "merged topic"
        merged_topic_ids = set()
        for g in binding_groups:
            for r in g["project_task_refs"]:
                if r.get("project_topic_id"):
                    merged_topic_ids.add(r["project_topic_id"])

        # Load previous_update state per merged topic
        from backend.services.project_topic_state import get_project_topic_state
        call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        project_id = call_row[0]["project_id"]
        all_state = get_project_topic_state(project_id, db=db)
        state_by_id = {t["topic_id"]: t for t in all_state}

        # Load pending tasks (this call's candidates)
        pending_row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
        pending = (pending_row[0] or {}).get("pending_topics") or []
        pending_tasks_by_topic_name = {p["name"].lower(): p.get("tasks", []) for p in pending}

        # Load past transcripts + current
        all_calls = db.table("calls").select("id, transcript, created_at").eq("project_id", project_id).order("created_at").execute().data
        transcripts = {
            c["id"]: ingest_transcript(c.get("transcript") or "")
            for c in all_calls if c.get("transcript")
        }

        # Resolve LLM config
        llm, model = _resolve_workflow_llm_for_category(project_id, "extract_topic_updates", db)

        # Synthesize per merged topic
        results = {}
        for topic_id in merged_topic_ids:
            topic = state_by_id.get(topic_id)
            if not topic:
                continue
            # Collect new bound tasks for this topic
            new_bound = []
            for g in binding_groups:
                pt_ids = {r.get("task_id") for r in g["project_task_refs"] if r.get("project_topic_id") == topic_id}
                if not pt_ids:
                    continue
                for r in g["call_task_refs"]:
                    name = (r.get("call_topic_name") or "").lower()
                    if not r.get("task_id"):
                        continue
                    for t in pending_tasks_by_topic_name.get(name, []):
                        if t.get("task_id") == r["task_id"]:
                            new_bound.append(t)
            if not new_bound:
                continue
            await plog.log(f"  → Synthesizing topic {topic['name']!r}…")
            r = await run_synthesize_merged_topic(
                topic_name=topic["name"],
                previous_update={"tasks": topic.get("tasks", []), "summary": topic.get("summary"),
                                 "status": topic.get("status"), "key_terms": topic.get("key_terms")},
                new_bound_tasks=new_bound,
                ingested_transcripts=transcripts,
                llm=llm, model=model, log_fn=plog.log,
            )
            results[topic_id] = r

        cache = {**results, "__progress__": plog.entries_snapshot()}
        db.table("calls").update({
            "extract_updates_cache": cache, "extract_updates_status": "done",
        }).eq("id", call_id).execute()
    except Exception as e:
        logger.exception(f"❌ [synthesize] failed for call {call_id}: {e}")
        db.table("calls").update({"extract_updates_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()
```

(Adapt to whatever the existing router orchestration shape is — this is the skeleton.)

- [ ] **Step 5: Run tests**

```bash
pytest backend/tests/test_topic_verification.py -v
```

Expected: new test PASS + prior tests unchanged.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: Pass 3 — run_synthesize_merged_topic (synthesis, not re-extraction) (Phase 4 complete)"
```

---

### Task 11 — Phase 5: Frontend task-matching component (replaces topic-level)

**Files:**
- Create: `frontend/src/components/TaskMatchingStage.tsx`
- Create: `frontend/src/components/TaskCard.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, add:

```typescript
// EPIC-19 — task-level matching
export interface TaskRef {
  call_topic_name?: string;
  project_topic_id?: string;
  task_id: string;
}

export type BindingKind = 'binding' | 'topic_merge';

export interface TaskMatchGroup {
  kind: BindingKind;
  call_task_refs: TaskRef[];
  project_task_refs: TaskRef[];
}
```

- [ ] **Step 2: Add API client method**

In `frontend/src/api/client.ts`:

```typescript
// EPIC-19
saveTaskMatches: async (callId: string, groups: TaskMatchGroup[]) => {
  return proxyFetch(`/api/calls/${callId}/topics/save-matches`, {
    method: 'POST',
    body: JSON.stringify(groups),
  });
},
```

- [ ] **Step 3: Implement TaskCard component**

Create `frontend/src/components/TaskCard.tsx`:

```typescript
"use client";

import React from 'react';

interface TaskCardProps {
  taskId: string;
  topicName: string;
  taskText: string;
  nextStep?: string;
  owner?: string;
  status?: string;
  keyTerms?: string[];
  isSelected?: boolean;
  isBound?: boolean;
  matchHint?: 'exact' | 'partial' | null;
  onClick?: () => void;
}

export function TaskCard({
  taskId, topicName, taskText, nextStep, owner, status, keyTerms,
  isSelected, isBound, matchHint, onClick,
}: TaskCardProps) {
  const border = isSelected ? 'border-blue-500' : isBound ? 'border-green-500' : 'border-gray-200';
  const bg = matchHint === 'exact' ? 'bg-yellow-50' : matchHint === 'partial' ? 'bg-orange-50' : 'bg-white';
  return (
    <div
      onClick={onClick}
      className={`p-2 border-2 rounded cursor-pointer ${border} ${bg} hover:shadow-md text-xs`}
      data-task-id={taskId}
    >
      <div className="text-gray-500 text-xs">{topicName}</div>
      <div className="font-medium">{taskText}</div>
      {nextStep && <div className="text-gray-600 mt-1">→ {nextStep}</div>}
      {owner && <div className="text-gray-500">Owner: {owner}</div>}
      {keyTerms && keyTerms.length > 0 && (
        <div className="text-gray-400 mt-1">{keyTerms.join(', ')}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Implement TaskMatchingStage component**

Create `frontend/src/components/TaskMatchingStage.tsx`:

```typescript
"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { TaskCard } from './TaskCard';
import { TaskMatchGroup, TaskRef } from '@/types';
import { topicsAPI } from '@/api/client';

interface Props {
  callId: string;
  existingTopics: Array<{topic_id: string, name: string, tasks: Array<{task_id: string, task: string, next_step?: string, owner?: string, key_terms?: string[]}>}>;
  candidateTopics: Array<{name: string, tasks: Array<{task_id: string, task: string, next_step?: string, owner?: string, key_terms?: string[]}>}>;
  onAdvance: () => void;
}

export function TaskMatchingStage({ callId, existingTopics, candidateTopics, onAdvance }: Props) {
  // groups: list of current bindings
  const [groups, setGroups] = useState<TaskMatchGroup[]>([]);
  // selection state: at most one candidate + one existing being staged for binding
  const [stagedCandidate, setStagedCandidate] = useState<TaskRef | null>(null);
  const [stagedExisting, setStagedExisting] = useState<TaskRef | null>(null);

  // Exact-text match hints (mechanical, no LLM)
  const matchHints = useMemo(() => {
    const existingTexts = new Map<string, string>();
    for (const t of existingTopics) {
      for (const task of t.tasks) {
        existingTexts.set(task.task.trim().toLowerCase(), task.task_id);
      }
    }
    const hints = new Map<string, 'exact' | 'partial'>();
    for (const t of candidateTopics) {
      for (const task of t.tasks) {
        if (existingTexts.has(task.task.trim().toLowerCase())) {
          hints.set(task.task_id, 'exact');
        }
      }
    }
    return hints;
  }, [existingTopics, candidateTopics]);

  function stageCandidate(ref: TaskRef) { setStagedCandidate(ref); }
  function stageExisting(ref: TaskRef) { setStagedExisting(ref); }
  function commitBinding() {
    if (!stagedCandidate || !stagedExisting) return;
    setGroups(g => [...g, {
      kind: 'binding',
      call_task_refs: [stagedCandidate],
      project_task_refs: [stagedExisting],
    }]);
    setStagedCandidate(null);
    setStagedExisting(null);
  }
  function clearStaging() { setStagedCandidate(null); setStagedExisting(null); }
  function markCandidateNew(ref: TaskRef) {
    setGroups(g => [...g, {kind: 'binding', call_task_refs: [ref], project_task_refs: []}]);
  }

  // Keyboard shortcuts: space = stage/commit, n = mark new, esc = clear
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === ' ') { e.preventDefault(); if (stagedCandidate && stagedExisting) commitBinding(); }
      if (e.key === 'Escape') clearStaging();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [stagedCandidate, stagedExisting]);

  async function save() {
    await topicsAPI.saveTaskMatches(callId, groups);
    onAdvance();
  }

  // Tasks not in any group → still candidate; tasks in a 'binding' with empty project_task_refs → new
  const isBound = (taskId: string) =>
    groups.some(g => g.call_task_refs.some(r => r.task_id === taskId)
                   || g.project_task_refs.some(r => r.task_id === taskId));

  return (
    <div className="flex gap-4 p-4">
      <div className="flex-1">
        <h3 className="font-semibold mb-2">Existing project tasks</h3>
        {existingTopics.map(t => (
          <div key={t.topic_id} className="mb-3">
            <div className="text-sm text-gray-600 mb-1">{t.name}</div>
            {t.tasks.map(task => (
              <TaskCard
                key={task.task_id}
                taskId={task.task_id}
                topicName={t.name}
                taskText={task.task}
                nextStep={task.next_step}
                owner={task.owner}
                keyTerms={task.key_terms}
                isSelected={stagedExisting?.task_id === task.task_id}
                isBound={isBound(task.task_id)}
                onClick={() => stageExisting({project_topic_id: t.topic_id, task_id: task.task_id})}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="flex-1">
        <h3 className="font-semibold mb-2">This call's candidate tasks</h3>
        {candidateTopics.map(t => (
          <div key={t.name} className="mb-3">
            <div className="text-sm text-gray-600 mb-1">{t.name}</div>
            {t.tasks.map(task => (
              <TaskCard
                key={task.task_id}
                taskId={task.task_id}
                topicName={t.name}
                taskText={task.task}
                nextStep={task.next_step}
                owner={task.owner}
                keyTerms={task.key_terms}
                matchHint={matchHints.get(task.task_id)}
                isSelected={stagedCandidate?.task_id === task.task_id}
                isBound={isBound(task.task_id)}
                onClick={() => stageCandidate({call_topic_name: t.name, task_id: task.task_id})}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="w-48 sticky top-4 self-start">
        <h3 className="font-semibold mb-2">Actions</h3>
        <button
          disabled={!stagedCandidate || !stagedExisting}
          onClick={commitBinding}
          className="w-full p-2 bg-blue-500 text-white rounded disabled:bg-gray-300 mb-2"
        >
          Bind ({stagedCandidate ? '1' : '0'} ↔ {stagedExisting ? '1' : '0'})
        </button>
        <button
          disabled={!stagedCandidate}
          onClick={() => { if (stagedCandidate) { markCandidateNew(stagedCandidate); setStagedCandidate(null); }}}
          className="w-full p-2 bg-green-500 text-white rounded disabled:bg-gray-300 mb-2"
        >
          Mark candidate NEW
        </button>
        <button onClick={clearStaging} className="w-full p-2 bg-gray-200 rounded mb-4">Clear staging</button>
        <hr className="my-2" />
        <div className="text-xs text-gray-600 mb-2">Groups: {groups.length}</div>
        <button onClick={save} className="w-full p-2 bg-purple-600 text-white rounded">
          Save matches → Project updates
        </button>
        <div className="text-xs text-gray-500 mt-2">
          Shortcuts: space = bind, esc = clear
        </div>
      </div>
    </div>
  );
}
```

(This is a minimum-viable component. N:M binding is supported by repeatedly committing bindings with the same existing task → multiple call_task_refs in separate groups, OR merging them at backend. v2 can add an explicit "extend current group" mode.)

- [ ] **Step 5: Wire into the page**

In `frontend/app/projects/[id]/calls/[call_id]/page.tsx`, find where `project_matching` stage is rendered. Replace with:

```tsx
import { TaskMatchingStage } from '@/components/TaskMatchingStage';

// ... inside stage routing logic ...
if (call.kanban_stage === 'project_matching') {
  return <TaskMatchingStage
    callId={call.id}
    existingTopics={existingTopicsWithTasks}
    candidateTopics={pendingTopicsFromCall}
    onAdvance={() => router.refresh()}
  />;
}
```

(Adapt to the existing stage routing pattern. Load `existingTopicsWithTasks` from `/api/projects/{id}/topics/prior-to-call/{call_id}` or whatever the existing endpoint is.)

- [ ] **Step 6: Typecheck + lint**

```bash
cd frontend
npx tsc --noEmit 2>&1 | tail -10
npm run lint 2>&1 | tail -10
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-19] feat: task-level matching UI (replaces topic-level project_matching)"
```

---

### Task 12 — Phase 5: Cross-topic binding modal

**Files:**
- Create: `frontend/src/components/CrossTopicBindingModal.tsx`
- Modify: `frontend/src/components/TaskMatchingStage.tsx`

- [ ] **Step 1: Implement modal**

Create `frontend/src/components/CrossTopicBindingModal.tsx`:

```typescript
"use client";

import React from 'react';

interface Props {
  candidateTopicName: string;
  existingTopicName: string;
  onChoose: (decision: 'keep_existing_topic' | 'keep_candidate_topic' | 'merge_topics' | 'cancel') => void;
}

export function CrossTopicBindingModal({ candidateTopicName, existingTopicName, onChoose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white p-4 rounded shadow-lg max-w-md">
        <h3 className="font-semibold mb-2">Cross-topic binding</h3>
        <p className="text-sm mb-4">
          You're binding a task from <strong>{candidateTopicName}</strong> to a task under <strong>{existingTopicName}</strong>.
          Which topic should the merged task live under?
        </p>
        <div className="flex flex-col gap-2">
          <button onClick={() => onChoose('keep_existing_topic')}
            className="p-2 bg-blue-500 text-white rounded">
            Keep under "{existingTopicName}" (existing wins)
          </button>
          <button onClick={() => onChoose('keep_candidate_topic')}
            className="p-2 bg-blue-400 text-white rounded">
            Move into "{candidateTopicName}" (candidate wins)
          </button>
          <button onClick={() => onChoose('merge_topics')}
            className="p-2 bg-purple-500 text-white rounded">
            These two topics are the same — merge them
          </button>
          <button onClick={() => onChoose('cancel')}
            className="p-2 bg-gray-200 rounded">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire modal into TaskMatchingStage**

In `frontend/src/components/TaskMatchingStage.tsx`, modify `commitBinding`:

```typescript
function commitBinding() {
  if (!stagedCandidate || !stagedExisting) return;
  // Cross-topic check
  const candidateTopic = stagedCandidate.call_topic_name?.toLowerCase();
  const existingTopic = existingTopics.find(t => t.topic_id === stagedExisting.project_topic_id);
  const existingTopicName = existingTopic?.name.toLowerCase();
  if (candidateTopic && existingTopicName && candidateTopic !== existingTopicName) {
    setShowCrossTopicModal({ candidate: candidateTopic, existing: existingTopicName });
    return;
  }
  // Same topic — just commit
  doCommitBinding();
}

function doCommitBinding(topicMergeDecision?: 'keep_existing' | 'keep_candidate' | 'merge') {
  if (!stagedCandidate || !stagedExisting) return;
  const newGroups = [...groups, {
    kind: 'binding' as const,
    call_task_refs: [stagedCandidate],
    project_task_refs: [stagedExisting],
  }];
  if (topicMergeDecision === 'merge') {
    // Emit an additional topic_merge group
    newGroups.push({
      kind: 'topic_merge' as const,
      call_task_refs: [{call_topic_name: stagedCandidate.call_topic_name!, task_id: ''}],
      project_task_refs: [{project_topic_id: stagedExisting.project_topic_id!, task_id: ''}],
    });
  }
  setGroups(newGroups);
  setStagedCandidate(null);
  setStagedExisting(null);
  setShowCrossTopicModal(null);
}
```

Add state: `const [showCrossTopicModal, setShowCrossTopicModal] = useState<{candidate: string, existing: string} | null>(null);`

Add modal render at top of return:

```tsx
{showCrossTopicModal && (
  <CrossTopicBindingModal
    candidateTopicName={showCrossTopicModal.candidate}
    existingTopicName={showCrossTopicModal.existing}
    onChoose={(decision) => {
      if (decision === 'cancel') { setShowCrossTopicModal(null); return; }
      doCommitBinding(decision === 'keep_existing_topic' ? 'keep_existing'
                      : decision === 'keep_candidate_topic' ? 'keep_candidate'
                      : 'merge');
    }}
  />
)}
```

- [ ] **Step 3: Typecheck + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-19] feat: cross-topic binding modal in task-matching UI"
```

---

### Task 13 — Phase 5: Keyboard navigation + exact-text pre-highlight polish

**Files:**
- Modify: `frontend/src/components/TaskMatchingStage.tsx`

- [ ] **Step 1: Add keyboard navigation**

Add to `TaskMatchingStage.tsx`:

```typescript
const [focusIndex, setFocusIndex] = useState<{column: 'existing' | 'candidate', topic: number, task: number}>({
  column: 'candidate', topic: 0, task: 0,
});

// j/k = down/up within column; h/l = switch columns; space = stage/commit; n = mark new
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.key === 'j') { e.preventDefault(); setFocusIndex(f => moveFocus(f, 1)); }
    if (e.key === 'k') { e.preventDefault(); setFocusIndex(f => moveFocus(f, -1)); }
    if (e.key === 'h' || e.key === 'l') { e.preventDefault(); setFocusIndex(f => ({...f, column: f.column === 'candidate' ? 'existing' : 'candidate'})); }
    if (e.key === 'Enter') { e.preventDefault(); stageFocused(); }
    if (e.key === ' ' && stagedCandidate && stagedExisting) { e.preventDefault(); commitBinding(); }
    if (e.key === 'n' && stagedCandidate) { e.preventDefault(); markCandidateNew(stagedCandidate); setStagedCandidate(null); }
    if (e.key === 'Escape') clearStaging();
  };
  window.addEventListener('keydown', handler);
  return () => window.removeEventListener('keydown', handler);
}, [stagedCandidate, stagedExisting, focusIndex]);
```

(Add `moveFocus` and `stageFocused` helpers that work with the topic/task structure.)

- [ ] **Step 2: Add a "Use exact-text matches" bulk action**

Add a button in the actions column that auto-stages all exact-text matches and commits them as N bindings:

```typescript
<button
  onClick={() => {
    const autoGroups: TaskMatchGroup[] = [];
    for (const t of candidateTopics) {
      for (const task of t.tasks) {
        if (matchHints.get(task.task_id) === 'exact') {
          // Find the existing task with matching text
          const candidateText = task.task.trim().toLowerCase();
          for (const et of existingTopics) {
            for (const etask of et.tasks) {
              if (etask.task.trim().toLowerCase() === candidateText) {
                autoGroups.push({
                  kind: 'binding',
                  call_task_refs: [{call_topic_name: t.name, task_id: task.task_id}],
                  project_task_refs: [{project_topic_id: et.topic_id, task_id: etask.task_id}],
                });
                break;
              }
            }
          }
        }
      }
    }
    setGroups(g => [...g, ...autoGroups]);
  }}
  className="w-full p-2 bg-yellow-500 text-white rounded mb-2"
>
  Auto-bind {Array.from(matchHints.values()).filter(h => h === 'exact').length} exact matches
</button>
```

- [ ] **Step 3: Typecheck + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-19] polish: keyboard nav + auto-bind exact matches in task-matching UI (Phase 5 complete)"
```

---

### Task 14 — Phase 6: Historical match group backfill script

**Files:**
- Create: `backend/scripts/migrate_match_groups_to_task_level.py`

- [ ] **Step 1: Write backfill script**

Create `backend/scripts/migrate_match_groups_to_task_level.py`:

```python
"""EPIC-19 — Backfill historical topic-level match_groups to task-level shape.

Old shape: {call_topic_names: [...], project_topic_ids: [...]}
New shape: {call_task_refs: [...], project_task_refs: [...], kind: 'binding'}

For each historical row: fan out all tasks of each call_topic_name AND all
tasks of each project_topic_id. Conservative — produces an N:M binding row
linking every old-side task to every new-side task. Manual review may be
needed for accuracy on important historical projects.

Usage:
  python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid> --dry-run
  python3 -m backend.scripts.migrate_match_groups_to_task_level --all
"""
from __future__ import annotations
import argparse
import sys

from backend.database.supabase_client import get_client


def backfill_for_call(call_id: str, dry_run: bool) -> dict:
    db = get_client()
    rows = db.table("topic_match_groups").select("*").eq("call_id", call_id).execute().data or []
    converted = 0
    for r in rows:
        # Already migrated?
        if r.get("call_task_refs") or r.get("project_task_refs"):
            continue
        old_names = r.get("call_topic_names") or []
        old_pids = r.get("project_topic_ids") or []
        # Fetch tasks for each side
        call_task_refs = []
        for name in old_names:
            # pending_topics for the call
            call_row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
            pending = (call_row[0] or {}).get("pending_topics") or []
            for t in pending:
                if (t.get("name") or "").lower() == name.lower():
                    for task in t.get("tasks") or []:
                        if task.get("task_id"):
                            call_task_refs.append({"call_topic_name": name, "task_id": task["task_id"]})
        project_task_refs = []
        for pid in old_pids:
            state_row = db.table("project_topic_state").select("tasks").eq("topic_id", pid).limit(1).execute().data
            tasks = (state_row[0] or {}).get("tasks") if state_row else []
            for task in (tasks or []):
                if task.get("task_id"):
                    project_task_refs.append({"project_topic_id": pid, "task_id": task["task_id"]})
        if dry_run:
            print(f"  would update group {r['id']}: {len(call_task_refs)} call refs + {len(project_task_refs)} project refs")
        else:
            db.table("topic_match_groups").update({
                "kind": "binding",
                "call_task_refs": call_task_refs,
                "project_task_refs": project_task_refs,
            }).eq("id", r["id"]).execute()
            converted += 1
    return {"call_id": call_id, "converted": converted, "total_rows": len(rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="UUID of single project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.project or args.all):
        print("error: --project <uuid> or --all required", file=sys.stderr)
        return 1

    db = get_client()
    q = db.table("calls").select("id, project_id")
    if args.project:
        q = q.eq("project_id", args.project)
    calls = q.execute().data or []
    print(f"📥 Found {len(calls)} call(s) to scan")
    total_converted = 0
    for c in calls:
        result = backfill_for_call(c["id"], args.dry_run)
        total_converted += result["converted"]
        print(f"  call {c['id']}: {result['converted']}/{result['total_rows']} group(s) backfilled")
    print(f"✅ Done. Total converted: {total_converted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke import**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -c "from backend.scripts.migrate_match_groups_to_task_level import main, backfill_for_call; print('imports ok')"
```

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] feat: backfill script — topic-level → task-level match groups"
```

---

### Task 15 — Phase 6: Migration runbook + session wrap-up docs

**Files:**
- Create: `docs/project/config/2026-05-25-epic-19-migration-runbook.md`
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/codebase.md`
- Modify: `docs/project/config/epics/ACTIVE.md`
- Modify: `workflow/ADR.md`
- Modify: `workflow/ERRORS.md` (if any bugs found mid-execution)

- [ ] **Step 1: Write migration runbook**

Create `docs/project/config/2026-05-25-epic-19-migration-runbook.md`:

```markdown
# EPIC-19 Migration Runbook

## Pre-flight
1. Apply migration 035 in Supabase Dashboard:
   ```sql
   -- Paste contents of backend/database/migrations/035_task_level_match_groups.sql
   ```
2. Verify the new columns exist:
   ```sql
   SELECT column_name FROM information_schema.columns WHERE table_name = 'topic_match_groups';
   ```
   Should include: call_task_refs, project_task_refs, kind

## Reset stale Pass 1/2/3 caches (per-project)
3. Dry run:
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> --dry-run
   ```
4. Actual reset:
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid>
   ```

## Backfill historical match_groups (per-project)
5. Dry run:
   ```bash
   python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid> --dry-run
   ```
6. Actual:
   ```bash
   python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid>
   ```

## Post-flight verification
7. Re-open a representative call in the UI:
   - project_matching: new task-level UI loads; existing tasks and candidates render
   - Pass 1 (if new_topics bucket non-empty): runs cleanly; verdict labels are `confirmed_new` / `suggest_merge_with`
   - Pass 2 (if old_untouched_topics non-empty): runs cleanly; uses line-range citations
   - Pass 3 (if merged_topics non-empty): produces synthesized topic_updates with citations
   - No "ungrounded items" or "rarity check failed" warnings (those are deleted)
```

- [ ] **Step 2: Update build-log.md**

Prepend to `docs/project/config/build-log.md` (above the existing 2026-05-25 EPIC-18 wrap entry):

```markdown
### 2026-05-25 — EPIC-19: Task-Level Project Matching + Narrowed 3-Pass Synthesis (code-complete / pending smoke)

**Goal:** Pivot from EPIC-18's topic-level verification (18-30% confidence on real data) to task-level manual matching with narrowed LLM safety-net + synthesis roles.

**STREAM 1 — Backend foundation (Tasks 1-3):**
- Migration 035: topic_match_groups extended with call_task_refs + project_task_refs + kind columns
- backend/services/task_match_persistence.py: load/save task-level match groups
- save_match_groups endpoint accepts task-level shape

**STREAM 2 — Pass 1 narrowing (Tasks 4-7):**
- Deleted run_verify_canonical_match (S2.2 — never triggered in prod)
- Deleted check_citation_rarity + sanity flag penalty stack (the 18% killer)
- Deleted check_reasoning_references_tasks
- Pass 1 prompt reframed: safety-net for user's manual decision, default to confirming
- Verdict vocabulary: confirmed_new / suggest_merge_with (legacy aliases kept)
- Dropped wrong_canonical fixture (scenario now handled by user matching)

**STREAM 3 — Pass 2 line-number migration (Task 8):**
- backend/prompts/verify_not_discussed.py: line-range citation contract
- run_verify_not_discussed accepts ingested transcript dict
- Pass 2 router ingests current transcript

**STREAM 4 — Pass 3 synthesis rewrite (Tasks 9-10):**
- backend/prompts/extract_topic_updates.py: synthesis prompt (no re-extraction)
- run_synthesize_merged_topic: inputs are bound tasks + previous update state + transcripts
- Per-topic LLM call (Q2 decision)
- Pass 3 router assembles synthesis inputs from match_groups + project_topic_state

**STREAM 5 — Frontend task-level matching UI (Tasks 11-13):**
- frontend/src/components/TaskMatchingStage.tsx: replaces topic-level project_matching
- frontend/src/components/TaskCard.tsx: per-task display
- frontend/src/components/CrossTopicBindingModal.tsx: cross-topic binding decision
- Keyboard nav (j/k/h/l/space/n/esc)
- Auto-bind exact-text matches bulk action
- Exact-text + partial-text pre-highlight (mechanical, no LLM)

**STREAM 6 — Migration + wrap (Tasks 14-15):**
- backend/scripts/migrate_match_groups_to_task_level.py
- docs/project/config/2026-05-25-epic-19-migration-runbook.md
- ADR-005 (task-level matching), ADR-006 (Pass 3 as synthesis)

**Decisions taken (Q1-Q5 from design Section 11):**
- Q1: Pass 1 + 2 parallel (no overlap)
- Q2: Pass 3 per-topic LLM call
- Q3: Cross-topic decisions as kind='topic_merge' rows
- Q4: Pass 3 input as structured JSON
- Q5: Frontend keyboard-first

**What EPIC-19 obsoleted (deleted from EPIC-18):**
- run_verify_canonical_match + VERIFY_CANONICAL_MATCH_PROMPT
- check_citation_rarity + check_reasoning_references_tasks
- Sanity flag penalty stack in compute_confidence
- Free-form quote citation in Pass 2 (replaced with line-numbers)
- Full re-extraction in Pass 3 (replaced with synthesis)

**What EPIC-19 preserved from EPIC-18:**
- project_topic_state view (ADR-003)
- Line-number citation pattern (ADR-004)
- v5 structured registry (V5-CORE)
- projects.context wiring (V5-CONTEXT)
- Verification asymmetry UX (auto_accept_eligible)
- Migration script pattern

**Pending smoke:** project a / call b + project b / call b end-to-end retest. Acceptance: Pass 1 `confirmed_new` ≥80% confidence, no `citations_lack_rare_terms` warnings, task matching UI usable in <10 min per call.

---
```

- [ ] **Step 3: Update codebase.md**

Prepend to `docs/project/config/codebase.md` "EPIC-18 additions" section a new "EPIC-19 additions" header listing the new modules + components.

- [ ] **Step 4: Update ACTIVE.md**

Replace `docs/project/config/epics/ACTIVE.md` current-story line:

```markdown
## Current Story
- **Active epic:** EPIC-19 — Task-level project matching + narrowed 3-pass synthesis (code-complete, pending smoke)
- **Branch:** `epic-16-rag-rework`
- **Status:** All 15 tasks landed. Migration 035 applied. Backfill ready.
- **Next:** Smoke test on project a + project b under the new pipeline.
```

- [ ] **Step 5: Append ADR-005 + ADR-006**

In `workflow/ADR.md`, add:

```markdown
## ADR-005 — Task-level manual matching at project_matching stage

**Date:** 2026-05-25
**Epic:** EPIC-19
**Status:** Accepted

### Context
EPIC-18's topic-level verification produced semantically-correct verdicts at 18-30% confidence due to sanity-stack compounding on a fuzzy unit (the topic). Real-data smoke on project a revealed the failure was structural: comparing topic blobs is fundamentally fuzzy.

### Decision
project_matching becomes task-level: users manually bind candidate tasks (from v5) to existing tasks (from project_topic_state) with N:M support. Cross-topic bindings surface a modal for the topic-shape decision. LLM-driven matching is removed from this stage entirely.

### Consequences
- User does identity work; LLM does only safety-net (Pass 1/2) + synthesis (Pass 3)
- 18-30% confidence problem dissolves (Pass 1 reflects actual match quality, no penalty stack)
- Smaller LLM cost (4 candidate topics × 1 call instead of 7 × full sanity-stack)
- Trade-off: user time at matching stage; acceptable at human-scale PMO use

### Alternatives considered
- Task-level LLM matching (still fragile; EPIC-18's failure modes recur at finer granularity)
- Embedding-based semantic matching (infra dependency; ROI unclear at scale of one PMO)

---

## ADR-006 — Pass 3 as synthesis from bound tasks, not re-extraction

**Date:** 2026-05-25
**Epic:** EPIC-19
**Status:** Accepted

### Context
EPIC-18 Pass 3 (`extract_topic_updates`) re-extracted task state from raw transcripts on every call. Heavy LLM work; produced spurious tasks when the LLM "discovered" things differently each call.

### Decision
Pass 3 receives the already-confirmed bindings (from matching + Pass 1/2 overrides) + previous topic_updates state + transcripts. It SYNTHESIZES the merged state — preserves task_id identity, updates fields based on new evidence. Does not re-discover or re-extract tasks.

### Consequences
- Task identity is stable across calls (task_id preserved)
- Pass 3 output is deterministic in structure (one row per merged topic, exact task list shape)
- LLM work narrower: synthesize + update, not extract
- Cross-call chronology is a derived view over the task_updates history

### Alternatives considered
- Keep re-extraction with stricter prompts (EPIC-15's chronology attempts — both dropped)
- Event-sourced task model (over-engineered for current scale)
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-19] docs: migration runbook + build-log + ADR-005/006 + ACTIVE.md (EPIC-19 code-complete)"
```

---

## Spec coverage self-review

Walking the design doc section by section:

| Spec section | Tasks covering it |
|---|---|
| §3.1 call_topics (no change) | (no tasks; v5 untouched) |
| §3.2 project_matching task-level | Tasks 1-3 (backend) + 11-13 (frontend) |
| §3.3 Pass 1 narrowed | Tasks 4-7 |
| §3.4 Pass 2 line-number migration | Task 8 |
| §3.5 Pass 3 synthesis | Tasks 9-10 |
| §4 Data model (migration 035) | Task 1 |
| §5 Frontend | Tasks 11-13 |
| §6 Deletes/preserves/builds | Distributed across all tasks |
| §7 Work order | Phases 1-6 (Tasks 1-15) |
| §8 Risks + kill switches | Implicit in TDD per task |
| §9 Acceptance criteria | Smoke test (post-Task 15) |
| §11 Open questions Q1-Q5 | Resolved in pre-execution decisions table at top |

**Placeholder scan:** No TBD/TODO. Some "adapt to existing pattern" notes for frontend wiring (e.g., Task 11 Step 5) — these are intentional because the existing pattern needs inspection, not invention.

**Type consistency:** `TaskMatchGroup` TypedDict in Python matches `TaskMatchGroup` TS interface (kind, call_task_refs, project_task_refs). `TaskRef` consistent across both. Verdict names (`confirmed_new`, `suggest_merge_with`) consistent in prompt + verification code.

---

## Execution

Plan saved to `docs/project/config/2026-05-25-epic-19-implementation-plan.md`.

**Recommended execution mode:** `superpowers:subagent-driven-development` — fresh subagent per task, your per-task check-in cadence preserved.

**Alternative:** `superpowers:executing-plans` — inline batch execution.

**Total estimated time:** ~11 days of focused work across 6 phases + 15 tasks.

**Pre-execution gate:** confirm the 5 default Q1-Q5 decisions (table at top) or override any of them before Task 1.
