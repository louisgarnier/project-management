# Story 9.7 — Rollback Updates + Integration Testing

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §5, §6
**Depends on:** Story 9.4, 9.5, 9.6

---

## Goal
Update rollback logic to handle M:N merge reversal (un-archive source topics, delete merged topic). Clear verification state on rollback. Write integration tests covering the full pipeline.

## Acceptance Criteria
- [ ] Rollback to `project_updates` clears `verification_cache` and `verification_status`
- [ ] Rollback to `project_matching` or earlier un-archives source topics and clears `merged_into_topic_id`
- [ ] Rollback to `project_matching` or earlier deletes merged-into topics created during this call
- [ ] `transcript_excerpt` preserved in `extraction_cache` during rollback to `call_topics`
- [ ] All existing rollback behavior preserved (regression)

## Tasks
- [ ] Update `rollback_to_stage()` to clear verification fields on rollback to `project_updates` or earlier
- [ ] Add un-merge logic: find topics with `merged_into_topic_id` pointing to topics first raised in this call, un-archive them
- [ ] Delete merged-into topics and their topic_updates on un-merge
- [ ] Write integration test: full pipeline extract → match M:N → merge → validate → rollback → verify un-merge
- [ ] Write integration test: rollback clears verification state
- [ ] Write integration test: rollback preserves transcript excerpts
- [ ] Write regression test: existing 1:N rollback behavior unchanged

## Dev Tests
- Integration: advance Call 2 through M:N merge → rollback to project_matching → source topics un-archived, merged topic deleted
- Integration: advance with verification → rollback to project_updates → verification_cache cleared
- Integration: rollback to call_topics → extraction_cache has transcript_excerpt fields
- Regression: existing rollback tests still pass
