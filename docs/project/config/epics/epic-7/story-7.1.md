# Story 7.1 — Topic Dashboard API

**Epic:** EPIC-7 — Topic Dashboard
**Maps to plan:** Slice 7
**Maps to PRD:** US-10, FR-11, FR-11b
**Status:** `pending`

---

## Goal
Railway FastAPI exposes full CRUD for the project-level Topic Dashboard. User can add, remove, edit topics and change their status at any time — not only during the Topics kanban stage.

## Acceptance Criteria
- [ ] `GET /api/projects/{project_id}/topics` returns all topics with full update history per topic:
  - `first_raised` (call title + date)
  - `status` (`active` · `decision_made` · `on_hold` · `closed`)
  - `latest_update` (most recent `topic_updates` row)
  - `follow_up_items` (from latest update)
  - `history` (all `topic_updates` rows in order)
- [ ] `POST /api/projects/{project_id}/topics` creates a new topic manually
- [ ] `PATCH /api/topics/{topic_id}` updates name and/or status
- [ ] `DELETE /api/topics/{topic_id}` deletes topic and all its updates

## Tasks
- [ ] Extend `backend/routers/topics.py` with PATCH and DELETE
- [ ] Update `GET /api/projects/{project_id}/topics` to return enriched shape (with history, first_raised, latest_update)
- [ ] Write tests: `backend/tests/test_topic_dashboard.py`

## Dev Tests
- `backend/tests/test_topic_dashboard.py`:
  - `GET` returns topics with history (at least `first_raised` field populated)
  - `POST` creates topic with `status='active'`
  - `PATCH` changes status to `'decision_made'`
  - `DELETE` removes topic and all `topic_updates` rows
