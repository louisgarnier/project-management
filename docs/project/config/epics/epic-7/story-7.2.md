# Story 7.2 — Step 1: Call Topics Extraction Endpoint

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `pending`

---

## Goal
A new endpoint extracts topics from the current call's transcript only — no previous project topics in the prompt. This eliminates the bias in the current single-shot extraction. Result is returned to the frontend without saving to DB.

## Acceptance Criteria
- [ ] `POST /api/calls/{id}/topics/extract_call` returns a flat topic list `[{name, summary, follow_up_items, decisions, status, owner, sentiment}]`
- [ ] Prompt contains only the transcript (no previous topics)
- [ ] Returns 404 if call not found, 422 if transcript is empty/null
- [ ] Does NOT save to DB, does NOT advance stage
- [ ] Backend test: happy path + no-transcript guard

## Tasks
- [ ] Add `extract_call_topics(call_id)` to `backend/services/topics_service.py`
- [ ] Add `POST /api/calls/{id}/topics/extract_call` to `backend/routers/topics.py`
- [ ] Write tests in `backend/tests/test_topics.py`

## Dev Tests
- `test_extract_call_topics_happy_path` — returns flat list
- `test_extract_call_topics_no_transcript` — returns 422
