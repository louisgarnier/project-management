# Story 10.1 — Lineage Helper + Merge-Prompt Fix

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.1, §6 Phase 1

---

## Goal
Introduce a single backend module that walks `merged_into_topic_id` recursively to collect every ancestor topic's history, and plug it into the merge prompt so M:N merges at any call depth see the full chronological evidence from every ancestor call.

## Acceptance Criteria
- [ ] New module `backend/services/topic_lineage.py` exposes `get_topic_lineage`, `get_lineage_topic_updates`, `get_lineage_match_groups`
- [ ] `get_topic_lineage(topic_id)` returns the current topic plus every ancestor reachable via `merged_into_topic_id` (order: current → immediate sources → their sources → …)
- [ ] Cycle guard: visited-set protects against cyclic merges (cannot happen by construction, but guard is present + asserted)
- [ ] `get_lineage_topic_updates(topic_id)` returns every `topic_updates` row across the lineage, enriched with `source_topic_id` and `source_topic_name`, ordered by `created_at` ascending
- [ ] `_load_transcript_excerpts` in `topics_service.py` is replaced by a call to `get_lineage_topic_updates`
- [ ] Per-call evidence block rendered by `_build_excerpt_context` now includes archived-ancestor rows, with a provenance line ("from archived topic: {name}") when the evidence came from a different topic_id
- [ ] All three merge paths (new-topics merge, 1:1 merge, M:N merge) use the lineage-aware excerpt builder
- [ ] Unit tests cover: linear 3-call history, M:N fan-in at Call 2 with Call 3 merge on the result, grand-merge chain (M:N → 1:1 → M:N)
- [ ] Regression: existing single-topic merges (no lineage) produce an identical prompt to the current implementation
- [ ] Logged: when a merge uses ancestor evidence, info log lists the ancestor topic IDs contributed

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
