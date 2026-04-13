# Story 7.3 — Step 2: Aggregate Endpoint

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `pending`

---

## Goal
A new endpoint takes the frontend's Step 1 flat topic list, fetches accumulated project topics for context, and runs a second LLM call to match them into three buckets. For Call 1 (no previous topics), it auto-saves and advances to artifacts. For Call 2+, it returns the 3-bucket result for review without saving.

## Acceptance Criteria
- [ ] `POST /api/calls/{id}/topics/aggregate` accepts `{topics: [{name, summary, ...}]}`
- [ ] Fetches existing project topics (name + summary + follow_up_items) as LLM context
- [ ] LLM prompt classifies into `followed_up / not_discussed / new_topics`
- [ ] `_reattach_id` applied to followed_up and not_discussed buckets
- [ ] **Call 1 (no previous topics):** saves all as new topics, advances stage to `artifacts`, returns `{"auto_advanced": true, "call_number": 1}`
- [ ] **Call 2+:** advances stage to `project_topics`, returns `{call_number, followed_up, not_discussed, new_topics}`
- [ ] Returns 404 if call not found
- [ ] Backend tests: Call 1 auto-advance, Call 2+ 3-bucket, 404 guard

## Tasks
- [ ] Add `aggregate_topics(call_id, call_topics)` to `backend/services/topics_service.py`
- [ ] Add `POST /api/calls/{id}/topics/aggregate` to `backend/routers/topics.py`
- [ ] Remove old `_extract_topics_impl` two-shot path (Call 2+ now uses two separate endpoints)
- [ ] Write tests in `backend/tests/test_topics.py`

## Dev Tests
- `test_aggregate_call1_auto_advances` — returns auto_advanced=true, stage is artifacts
- `test_aggregate_call2_returns_buckets` — returns 3 buckets, stage is project_topics
- `test_aggregate_404` — call not found
