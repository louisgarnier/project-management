# Story 15.7 — Per-item Lifecycle + Chronology + RAG Verification + Accumulator

**Epic:** EPIC-15 — Call Topics Rebuild (Phase 2 / P2-C)
**Status:** [x] code-complete (2026-05-19) — awaiting user smoke (chronology generation on project_updates commit)
**Spec:** `docs/project/config/2026-05-18-epic-15-phase-2-architecture.md` §3 (lifecycle), §4.1 (chronology service + accumulator), §6 (commit-time freeze), §7 (LLM seams), §8 (perf)
**PRD:** `docs/project/config/2026-05-18-epic-15-phase-2-prd.md` G6, G7, G8, US-P2-04, US-P2-05, FR-P2-07/08/09, NFR-P2-02, NFR-P2-03, Q1, Q2
**Blocks:** 15.8 (xlsx exporter reads chronology + lifecycle metadata)
**Depends on:** 15.5 (new JSONB columns must exist) and 15.6 (artifact library entries use 4-value context_scope, so the new chronology LLM types can be seeded with `this_call_topics`)

## Goal
Add per-item lifecycle stamping (`closed_in_call_id` on tasks + open_questions when status flips → resolved, latest wins per Q1). Generate frozen chronology narratives (2–3 sentence summaries, ≤ 400 chars) + RAG verification notes for every (topic × call) pair at `project_updates` stage commit, via two new LLM artifact types. Persist results to the new `topic_updates` columns. Pipeline must not block on LLM failure (NFR-P2-03).

## Acceptance Criteria

### Backend — per-item lifecycle
- [ ] `backend/services/topics_service.py`:
  - [ ] New helper `_apply_lifecycle_on_resolve(prev_items, new_items, current_call_id)` — for `tasks[]` and `open_questions[]`:
    - On status transition `non-resolved → resolved`, set `closed_in_call_id = current_call_id`.
    - On any subsequent `non-resolved → resolved` transition, **overwrite** `closed_in_call_id` with the new call's id (latest wins per Q1).
    - On status transition `resolved → non-resolved`, clear `closed_in_call_id = null`.
  - [ ] `_persist_topic_update` calls the helper before write, sourcing `prev_items` from the prior call's `topic_updates` row for the same project_topic_id.
  - [ ] Decisions are immutable → no lifecycle stamping for them post-commit; their `added_in_call_id` doubles as decided-in.

### Backend — chronology prompt + service
- [ ] `backend/prompts/chronology.py` — NEW:
  - [ ] `CHRONOLOGY_NARRATIVE_PROMPT_BODY` — instructs LLM to write a 2–3 sentence summary of what happened to a given topic in a given call. Hard cap: 3 sentences / 400 chars. Asks model to anchor in the transcript excerpt provided.
  - [ ] `CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY` — given (narrative, transcript_excerpt), returns either `"verified"` or a short drift note ("YYYY-MM-DD narrative claims X but transcript does not contain X"). Prompt explicitly asks model to quote the transcript before claiming verified (anti-hallucination, per §7).
- [ ] `backend/services/chronology_service.py` — NEW:
  - [ ] `generate_chronology_cell(project_topic_id, call_id, db) -> (narrative, rag_note)`:
    1. Load the `topic_updates` row for this `(project_topic_id, call_id)`. If absent → return `(None, None)` (skip).
    2. Resolve LLM provider/model from artifact_library row `Chronology Narrative` (system-default).
    3. Call LLM #1 → narrative; truncate to **600 chars defensively** server-side (prompt cap is 400, the 600 guards against misbehaviour).
    4. Call LLM #2 → RAG verification, given the narrative + the relevant transcript excerpt(s) from the `topic_updates.evidence` field.
    5. Persist both to `topic_updates.chronology_narrative` + `topic_updates.rag_verification_note`.
  - [ ] On any failure: persist `chronology_narrative = ""` + `rag_verification_note = "(generation failed: <reason>)"` so the pipeline does not block (NFR-P2-03).
  - [ ] Structured log line: `🧬 [Chronology] topic={uuid} call={uuid} narrative_chars=N rag_status={verified|drift|failed} latency_ms=...`.

### Backend — library seed (2 new system entries)
- [ ] `backend/library/seed.py::SYSTEM_LIBRARY` — add 2 new entries (both `kind=llm`, `seeded_by_default=true`):
  - [ ] `Chronology Narrative` — category `chronology` (new category — register if needed). `context_scope='this_call_topics'`. `llm='openrouter'`, `model='deepseek/deepseek-v3.2'`.
  - [ ] `RAG Verification` — category `chronology`. Same provider/model.
- [ ] `upsert_system_library` is idempotent — re-running on a project that already has the entries no-ops.

### Backend — accumulator hook
- [ ] `backend/services/topic_updates_accumulator.py` — NEW (or extend an existing service if one fits):
  - [ ] `accumulate_into_project_state(call_id, db)` triggered at `project_updates` stage commit. For each `topic_updates` row touched in this call:
    1. Defensively re-stamp `added_in_call_id` on any items missing it (idempotent).
    2. Apply `_apply_lifecycle_on_resolve` versus the prior call's row.
    3. Trigger `chronology_service.generate_chronology_cell(project_topic_id, call_id, db)`.
  - [ ] Chronology generation runs concurrently across topics via `asyncio.gather` with bounded concurrency **≤ 8 parallel LLM calls** (§10, avoid OpenRouter rate-limit storms).
  - [ ] Target wall-clock: < 60s per commit on a 12-topic call (NFR-P2-02). Log the total wall-clock at INFO.

### Backend — wire-up
- [ ] The existing aggregate / project_updates commit endpoint (`POST /api/calls/{id}/topics/aggregate` per architecture §5) calls `accumulate_into_project_state(call_id, db)` after the topic_updates rows are persisted.
- [ ] Reads of `topic_updates` everywhere include the 2 new chronology columns (sweep done in 15.5; verify no read-path regressions here).

### Tests
- [ ] `backend/tests/test_topic_lifecycle.py` — NEW:
  - [ ] Open→resolved flip stamps `closed_in_call_id` to current call.
  - [ ] Resolved→open clears `closed_in_call_id`.
  - [ ] Open→resolved→open→resolved stamps the *latest* resolving call (Q1).
- [ ] `backend/tests/test_chronology_service.py` — NEW:
  - [ ] Narrative truncated to 600 chars on misbehaving model output.
  - [ ] LLM-failure path persists `""` + `"(generation failed: ...)"` (NFR-P2-03).
  - [ ] RAG drift case writes the drift note verbatim.
  - [ ] `generate_chronology_cell` skips cleanly when `topic_updates` row absent.
- [ ] `backend/tests/test_topic_updates_accumulator.py` — NEW:
  - [ ] Concurrency bounded at ≤ 8 (mock LLM with semaphore probe).
  - [ ] Lifecycle stamping happens before chronology generation (chronology sees latest state).
- [ ] Full backend suite green; library seed idempotency test extended for the 2 new entries.

## Out of scope (handled in other stories)
- xlsx export of chronology cells → Story 15.8.
- ProjectTrackerTab UI rendering of chronology → Story 15.8.
- Re-trigger UX for failed chronology rows → deferred (manual SQL for now; documented as known limitation §9).
- Closed-OQ UX polish in CallTopicsStage → deferred per architecture §9.

## Notes
- Chronology is **frozen at commit** (Q-pin in architecture §6). If extraction is later corrected and re-run, narratives become stale until manual re-trigger — documented limitation, acceptable for v1.
- The accumulator must run *after* `_persist_topic_update` writes the latest rows; otherwise lifecycle stamping reads stale prev-state.
