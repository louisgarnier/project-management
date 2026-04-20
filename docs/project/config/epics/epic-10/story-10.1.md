# Story 10.1 — Lineage Helper + Merge-Prompt Fix

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `done` — 2026-04-20
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.1, §6 Phase 1
**Plan:** `docs/project/config/2026-04-20-story-10.1-lineage-helper-plan.md`

---

## Goal
Introduce a single backend module that walks `merged_into_topic_id` recursively to collect every ancestor topic's history, and plug it into the merge prompt so M:N merges at any call depth see the full chronological evidence from every ancestor call.

## Acceptance Criteria
- [x] New module `backend/services/topic_lineage.py` exposes `get_topic_lineage`, `get_lineage_topic_updates`, `get_lineage_match_groups` (also `build_lineage_evidence_block` for rendering)
- [x] `get_topic_lineage(topic_id)` returns the current topic plus every ancestor reachable via `merged_into_topic_id` (BFS order: current → immediate sources → their sources → …)
- [x] Cycle guard: visited-set protects against cyclic merges (tested via `test_lineage_cycle_guard_terminates`)
- [x] `get_lineage_topic_updates(topic_id)` returns every `topic_updates` row across the lineage, enriched with `source_topic_id`, `source_topic_name`, and `call_title`, ordered by `created_at` ascending
- [x] `_load_transcript_excerpts` in `topics_service.py` removed; merge paths now call `build_lineage_evidence_block`
- [x] Per-call evidence block includes archived-ancestor rows with a `(from archived topic: {name})` provenance line when evidence came from a different topic_id
- [x] Both merge call sites in `run_merge_preview` (1:1 and M:N) use the lineage-aware builder. Note: the new-topics-only path (no ptids) does not call the excerpt builder because it merges only call topics — no lineage applicable.
- [x] Unit tests cover: no-merge, M:N fan-in, multi-level chain (2 levels deep), cycle guard, chronological ordering, provenance on ancestor rows, fallback on empty history, match-group lineage filtering, plus a full integration test (`test_build_block_for_merged_topic_includes_call1_excerpt_from_archived_source`)
- [x] Regression: all 28 existing tests in `test_topics.py` still pass unchanged after the refactor
- [x] Logged: `db_logger.info("🧬 [Lineage] Evidence for topic {id} ({name}) includes {N} ancestor(s): [...]")` fires when ancestor evidence is included

## Tasks
- [ ] Create `backend/services/topic_lineage.py` with the three helpers and docstrings
- [ ] Write unit tests in `backend/tests/test_topic_lineage.py`:
  - `test_lineage_no_merges_returns_self_only`
  - `test_lineage_single_mn_merge_returns_sources`
  - `test_lineage_chain_of_merges_returns_full_chain`
  - `test_lineage_updates_ordered_chronologically`
  - `test_lineage_updates_tagged_with_source_topic`
  - `test_cycle_guard_raises_or_terminates`
- [ ] Replace `_load_transcript_excerpts` inline in `topics_service.py` with delegation to `get_lineage_topic_updates`
- [ ] Update `_build_excerpt_context` to render `source_topic_name` provenance line when it differs from the current topic name
- [ ] Add integration test `test_mn_merge_then_subsequent_call_sees_ancestor_excerpt` that seeds Call 1 → Call 2 M:N merge → Call 3 merge, and asserts Call 1's excerpt appears in the Call 3 merge prompt
- [ ] Verify existing Epic 9 tests still pass

## Dev Tests
- Seed a project with 3 calls, each touching the same topic; M:N-merge two topics at Call 2; run merge at Call 3; capture the generated prompt via log and assert all three calls' excerpts are present.
- Assert the provenance line appears for evidence originating from an archived topic id.
- Confirm the single-topic (no-lineage) case emits an identical prompt to pre-change.

## Out of Scope
- Evidence API endpoint (Story 10.3)
- Frontend evidence panel (Story 10.4)
- Prompt audit doc (Story 10.2)
- Concrete fixes to verification / artifact prompts (Story 10.6)

## Completion
- **Completed:** 2026-04-20
- **Commits:** `026c736`, `4958152`, `f0cfcee`, `e460d87`, `e4f9a49`, `dbabdb1`, `3ec14cd`, `99022bc` (all `[EPIC-10]` prefix)
- **Test coverage:** 9 tests in `backend/tests/test_topic_lineage.py`; all 28 `test_topics.py` tests unchanged; 37/37 topics+lineage tests green (1.06s).
- **Known pre-existing failures (not caused by this story):** 4 tests in `test_artifact_types.py`, `test_artifacts.py`, `test_calls.py` fail on both pre- and post-story SHAs — tracked separately.
- **Manual smoke verification:** deferred to next live merge — look for `🧬 [Lineage]` log line in `logs/backend_*.log` when running a merge on a topic with M:N ancestors.
