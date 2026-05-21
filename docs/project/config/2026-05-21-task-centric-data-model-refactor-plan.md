# Task-Centric Data Model Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the topic/task data model so per-task ownership of key_terms, open_questions, decisions, citations becomes the source of truth. Topics become thin containers.

**Architecture:** 5-phase rollout. Each phase shippable independently. Backward-compat reads pull legacy topic-level fields when per-task fields are absent. No DB schema migration needed (tasks JSONB accommodates the extra fields).

**Reference spec:** `docs/project/config/2026-05-21-task-centric-data-model-refactor-design.md`

---

## File Structure

**Backend modified:**
- `backend/prompts/call_topics.py` — new CALL_TOPICS_V4_PROMPT_BODY
- `backend/library/seed.py` — seed v4 library entry, soft-deprecate v3
- `backend/services/topics_service.py` — `_validate_topic`, `_stamp_item_ids`, `_persist_topic_update`, `list_call_topics`
- `backend/services/topic_verification.py` — `effective_token_set`, `_build_verify_new_prompt`, `_build_extract_updates_prompt`

**Backend tests:**
- `backend/tests/test_topics_service.py` — new validator paths
- `backend/tests/test_topic_verification.py` — new aggregation logic

**Frontend modified:**
- `frontend/src/types/index.ts` — TaskData richer
- `frontend/src/components/CallTopicsStage.tsx` — per-task rendering
- `frontend/src/components/ProjectUpdatesStage.tsx` — aggregation reads

---

## Phase 1 — Foundation: backend extraction + types

### Task 1.1 — v4 prompt body

**Files:**
- Modify: `backend/prompts/call_topics.py`

- [ ] Add CALL_TOPICS_V4_PROMPT_BODY at the bottom of the file. Schema differs from v3 in that each task object now carries `key_terms`, `open_questions`, `decisions`, `citations`. Topic loses `key_terms`, `open_questions`, `decisions`, `evidence` (keep name + importance only).

- [ ] Required fields list updated: task.key_terms (>=1 entry, list of strings), task.open_questions (optional, list of dicts), task.decisions (optional, list of dicts), task.citations (>=1 entry, list of dicts).

- [ ] Anti-pattern note: do NOT emit topic-level key_terms / OQ / decisions / evidence in v4. The topic is a container; tasks own the data.

- [ ] Commit:
  ```
  python3 scripts/git_ops.py commit "[EPIC-16] feat: CALL_TOPICS_V4_PROMPT_BODY — task-centric schema (each task carries key_terms, OQ, decisions, citations; topic carries only name + importance + tasks[])"
  ```

### Task 1.2 — Library v4 entry

**Files:**
- Modify: `backend/library/seed.py`

- [ ] Add a new SYSTEM_LIBRARY entry: name "Call Topics — v4 (task-centric)", category "call_topics", seeded_by_default=True. Soft-deprecate the v3 entry by setting its `seeded_by_default=False`.

- [ ] Tests in test_library_seed.py: assert v4 entry exists and is seeded.

- [ ] Commit:
  ```
  python3 scripts/git_ops.py commit "[EPIC-16] feat: register v4 call_topics library entry as default; demote v3"
  ```

### Task 1.3 — Validator + stamper updates

**Files:**
- Modify: `backend/services/topics_service.py`

- [ ] `_validate_topic`: accept task.key_terms (list[str]), task.open_questions (list[dict] with text/status/owner), task.decisions (list[dict] with text). All optional for backward compat. If a v4 topic has empty topic-level key_terms but tasks have them, accept (don't fail on missing topic.key_terms).

- [ ] `_stamp_item_ids`: extended to stamp per-task OQ ids + per-task decision ids (existing logic stamps topic-level OQ + decisions; add a per-task pass).

- [ ] `_persist_topic_update`: writes tasks JSONB with per-task richness. At write time, aggregates per-task OQ/decisions/key_terms into topic-level columns for backward-compat reads (UNION across tasks).

- [ ] Tests: 4 new tests in test_topics_service.py covering per-task validator paths + aggregation behavior.

- [ ] Commit:
  ```
  python3 scripts/git_ops.py commit "[EPIC-16] feat: _validate_topic + _stamp_item_ids + _persist_topic_update support per-task key_terms/OQ/decisions; aggregate to topic-level on write for back-compat reads"
  ```

### Task 1.4 — TaskData type

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] TaskData gains: `key_terms?: string[]`, `open_questions?: OpenQuestionData[]`, `decisions?: DecisionData[]`. Optional for backward compat. TaskCitation already exists.

- [ ] Commit:
  ```
  python3 scripts/git_ops.py commit "[EPIC-16] feat(types): TaskData gains optional key_terms/open_questions/decisions for task-centric model"
  ```

---

## Phase 2 — CallTopicsStage UI: per-task rendering

### Task 2.1 — Per-task key_terms chips

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] Each task row gets its own key_terms chip strip below the task input. Editable (add/remove chips per task).

- [ ] Topic-level key_terms column hidden when at least one task has per-task key_terms; else falls back to legacy display.

- [ ] Commit.

### Task 2.2 — Per-task open_questions list

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] Each task row gets a mini list of open_questions below the row. Add/edit/remove inline.

- [ ] Hide topic-level OQ section in v4 mode (when tasks have OQ data).

- [ ] Commit.

### Task 2.3 — Per-task decisions list

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] Each task row gets a mini list of decisions below the row. Add/edit/remove inline.

- [ ] Hide topic-level decisions section in v4 mode.

- [ ] Commit.

### Task 2.4 — Topic header thinning

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] Topic header (first row of topic block) shows: name + importance + computed counts ("3 tasks · 5 OQ · 2 decisions").

- [ ] Right-click menu unchanged.

- [ ] Commit.

---

## Phase 3 — Move task migration verification

### Task 3.1 — Verify move-task transfers all per-task data

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx` (existing move-task handler)

- [ ] Inspect current move-task: it already moves the full task object. Verify key_terms, OQ, decisions, citations transfer correctly. Adjust if any field is dropped.

- [ ] Add 1 test or manual verification step.

- [ ] Commit if any code changes; else just mark verified.

---

## Phase 4 — Pass ① + ③ adapted

### Task 4.1 — effective_token_set aggregates per-task key_terms

**Files:**
- Modify: `backend/services/topic_verification.py`

- [ ] `effective_token_set(topic_or_candidate)` now reads per-task key_terms when present (union across all tasks) + topic-level fallback. Topic name tokens still added.

- [ ] Tests: 2 new tests in test_topic_verification.py covering per-task aggregation.

- [ ] Commit.

### Task 4.2 — Pass ① prompt input per-task

**Files:**
- Modify: `backend/services/topic_verification.py::_build_verify_new_prompt`

- [ ] When sending existing project topics to the LLM, include each task with its per-task key_terms/OQ/decisions instead of (or in addition to) topic-level aggregates.

- [ ] Update the prompt's `EXISTING PROJECT TOPICS` section header to describe the new shape.

- [ ] Commit.

### Task 4.3 — Pass ③ output schema per-task

**Files:**
- Modify: `backend/prompts/extract_topic_updates.py`
- Modify: `backend/services/topic_verification.py::run_extract_topic_updates`

- [ ] Prompt output schema: `extracted_snapshot.tasks[i]` carries its own key_terms/OQ/decisions/citations. No more top-level OQ/decisions on extracted_snapshot (or aggregate them from tasks for back-compat display).

- [ ] `_collect_citations` updated to gather from per-task fields.

- [ ] Tests adjusted.

- [ ] Commit.

---

## Phase 5 — Cleanup

### Task 5.1 — Stop writing topic-level redundant fields

**Files:**
- Modify: `backend/services/topics_service.py::_persist_topic_update`

- [ ] Remove the aggregation step that populates topic-level OQ/decisions/key_terms columns from per-task data. New rows have those columns empty.

- [ ] Backward-compat reads (frontend + Pass ① fallback) handle empty topic-level OK.

- [ ] Commit.

### Task 5.2 — Deprecate legacy topic-level rendering

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`
- Modify: `frontend/src/components/ProjectUpdatesStage.tsx`

- [ ] Remove the topic-level OQ/decisions/key_terms sections from new-render paths. Keep guard for legacy data (display in read-only).

- [ ] Commit.

### Task 5.3 — Documentation

**Files:**
- Modify: `docs/project/config/codebase.md`
- Modify: `docs/project/config/build-log.md`

- [ ] Document the new task-centric model in codebase.md.

- [ ] Add a build-log entry summarizing the refactor.

- [ ] Commit.

---

## Self-review (post-write)

- ✅ All phases are independently shippable + reversible.
- ✅ No DB schema migration required (tasks JSONB accepts new fields).
- ✅ Backward-compat reads pull legacy topic-level fields when per-task fields are absent.
- ✅ Tests cover per-task validator + aggregation.
- ⚠️ Risk: LLM v4 prompt quality unknown until tested with real call. Phase 1.2 test = re-extract a known call after v4 deployment.

## Execution handoff

Each phase is a logical chunk. Recommended cadence:
- Phase 1 complete → user re-extracts a call → confirms data shape OK → next phase
- Phase 2 → user smoke-tests CallTopicsStage in browser → next
- Phase 3 → manual verification (move a task, inspect destination)
- Phase 4 → re-run Pass ① on existing call → confirm scoring sensible
- Phase 5 → cleanup; final verification
