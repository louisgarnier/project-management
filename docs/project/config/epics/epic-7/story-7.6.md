# Story 7.6 — Artifact Context: Inject Project Topics

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `done` — 2026-04-14

---

## Goal
Artifact generation automatically receives a compact summary of the project's current open topics as additional context, so outputs like Executive Summary and Next Steps are grounded in the full project history — not just this call.

## Acceptance Criteria
- [ ] Artifact SSE generation endpoint fetches open/in_progress project topics before calling LLM
- [ ] Compact topic summary appended to the LLM prompt context (after transcript, before artifact prompt)
- [ ] Format: topic name + latest summary + open follow_up_items (max 3 per topic)
- [ ] Resolved topics excluded from summary
- [ ] If no open topics: no context appended (graceful)
- [ ] Existing artifact generation tests still pass

## Tasks
- [ ] Add `get_project_topics_context(project_id, db) -> str` helper to `backend/services/topics_service.py`
- [ ] Call it in `backend/routers/artifacts.py` SSE stream endpoint before LLM generation
- [ ] Update `backend/tests/test_artifacts.py` to verify context injection

## Dev Tests
- `test_artifact_generation_includes_topic_context` — mock returns open topics, verify they appear in prompt
- `test_artifact_generation_no_topics_no_context` — no topics → no context appended, generation still works
