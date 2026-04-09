# Story 3.1 — Calls API with Sequential Enforcement

**Epic:** EPIC-3 — Kanban Board & Calls
**Maps to plan:** Slice 3
**Maps to PRD:** US-07, FR-03, FR-09b
**Status:** `done`

---

## Goal
Railway FastAPI manages calls per project. Creating a second call while one is active returns 409. The kanban pipeline stages are enforced at the API level.

## Acceptance Criteria
- [x] `GET /api/projects/{project_id}/calls` returns all calls for the project
- [x] `POST /api/projects/{project_id}/calls` creates a call with title; sets `kanban_stage = 'transcript'`
- [x] `POST` returns 409 with message `"Complete the current call before creating a new one"` if any call in the project is not `'done'`
- [x] `GET /api/calls/{call_id}` returns full call detail
- [x] `PATCH /api/calls/{call_id}/stage` advances `kanban_stage` (validated: must follow `transcript → artifacts → topics → done` order)
- [x] All operations logged via `db_logger`

## Tasks
- [x] Create `backend/routers/calls.py` with all endpoints
- [x] Implement sequential enforcement check in POST (query for non-done calls, return 409 if found)
- [x] Implement stage advancement validation in PATCH (reject out-of-order transitions)
- [x] Register router in `backend/main.py`
- [x] Write tests: `backend/tests/test_calls.py`

## Dev Tests
- `backend/tests/test_calls.py`:
  - `POST` with no active call → 201, `kanban_stage = 'transcript'`
  - `POST` with one active call → 409
  - `PATCH /stage` `transcript → artifacts` → 200
  - `PATCH /stage` `transcript → done` (skip) → 422
  - `GET` returns list including the new call
