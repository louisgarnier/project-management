# Story 6.1 — Topics API

**Epic:** EPIC-6 — Topics Stage
**Maps to plan:** Slice 6
**Maps to PRD:** US-06, FR-08, FR-09, FR-09b, FR-10
**Status:** `pending`

---

## Goal
Railway FastAPI handles topic extraction (via Claude or manual) and validates the call to Done. On Call 2+, previous validated topics are passed as context to Claude.

## Acceptance Criteria
- [ ] `POST /api/calls/{call_id}/topics/extract` triggers Claude extraction (only when explicitly called — NFR-08)
  - Call 1: extracts fresh from transcript + artifact contents
  - Call 2+: fetches validated topics from previous Done call in the project, passes as context
  - Returns list of `{name, summary, follow_up_items}` for user review
  - Uses `claude-sonnet-4-6`
- [ ] `POST /api/calls/{call_id}/topics` saves the user-validated topic list:
  - New topics → inserted into `topics` table with `first_raised_call_id`
  - Updates to existing topics → new row in `topic_updates` table
- [ ] `POST /api/calls/{call_id}/topics/validate` advances `kanban_stage` to `'done'`
  - Returns 422 if no topics exist for this call
- [ ] `GET /api/projects/{project_id}/topics` returns all topics with their full update history (for Topic Dashboard)
- [ ] All Claude calls logged via `claude_logger`

## Tasks
- [ ] Create `backend/services/topics_service.py` — `extract_topics(call_id, db) → list` and `get_previous_topics(project_id, db) → list`
- [ ] Create `backend/routers/topics.py` — POST /extract, POST / (save), POST /validate, GET
- [ ] Register router in `backend/main.py`
- [ ] Write tests: `backend/tests/test_topics.py` (mock Claude)

## Dev Tests
- `backend/tests/test_topics.py`:
  - `POST /extract` Call 1 → Claude called with transcript, returns topic list (mocked)
  - `POST /extract` Call 2 → Claude called with previous topics as context
  - `POST /` (save topics) → topic rows created in DB
  - `POST /validate` with topics present → call advances to `'done'`
  - `POST /validate` with no topics → 422
