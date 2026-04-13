# Story 8.1 — Topics Timeline Backend

**Epic:** EPIC-8 — Topics Timeline Grid
**Status:** `pending`

---

## Goal
A new endpoint returns the full topic × call matrix so the frontend can render the timeline grid without any computation. Each cell is pre-classified as new / followed_up / not_discussed / absent.

## Acceptance Criteria
- [ ] `GET /projects/{id}/topics/timeline` returns:
  ```json
  {
    "calls": [{"id", "title", "number", "kanban_stage"}],
    "topics": [{
      "topic_id", "name", "status", "owner", "sentiment",
      "first_raised_call_id",
      "call_updates": {
        "<call_id>": {"type": "new|followed_up|not_discussed", "summary?", "follow_up_items?", "decisions?", "status?", "owner?", "sentiment?"}
      }
    }]
  }
  ```
- [ ] Call_id absent from `call_updates` = topic did not yet exist at that call
- [ ] `not_discussed` cells contain only `{"type": "not_discussed"}`
- [ ] Backend tests: empty project, new + not_discussed, followed_up + absent

## Tasks
- [ ] Add `list_topics_timeline(project_id, db)` to `backend/services/topics_service.py`
- [ ] Add `GET /projects/{id}/topics/timeline` to `backend/routers/topics.py`
- [ ] Write 3 tests in `backend/tests/test_topics.py`

## Dev Tests
- `TestTopicsTimeline.test_timeline_no_topics`
- `TestTopicsTimeline.test_timeline_new_and_not_discussed`
- `TestTopicsTimeline.test_timeline_followed_up_and_absent`
