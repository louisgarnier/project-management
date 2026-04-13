# Story 6.1 — Topics API

**Epic:** EPIC-6 — Topics Stage
**Maps to plan:** Slice 6
**Maps to PRD:** US-06, FR-08, FR-09, FR-09b, FR-10
**Status:** `pending`

---

## Goal
Railway FastAPI handles topic extraction (via Claude or manual) and validates the call to Done. On Call 2+, previous validated topics are passed as context to Claude.

## Topic data model
Each topic has these fields — confirmed 2026-04-13:

| Field | Type | Notes |
|---|---|---|
| `name` | string | Topic label |
| `summary` | string | What was discussed on this call |
| `follow_up_items` | string[] | Action items before next call |
| `decisions` | string[] | Agreements / decisions reached (permanent record, never overwritten) |
| `status` | enum | `open` / `in_progress` / `resolved` — may change call-to-call |
| `owner` | string | Who owns follow-ups: `"Us"` / `"Client"` / `"Both"` |
| `sentiment` | enum | `positive` / `neutral` / `concern` — helps Claude surface risk on next call |
| `calls_open` | int | Number of consecutive calls this topic has been non-resolved (staleness counter) |
| `archived` | bool | Soft-deleted; removed from active views but kept in history |

> **⚠️ Before coding:** Check that the DB schema (`topics` + `topic_updates` tables in `backend/database/migrations/001_initial_schema.sql`) covers all fields above. Add a migration for `decisions`, `calls_open`, and `archived` if missing.

---

## Three-bucket sequencing (Call 2+)

When extracting topics for Call N (N ≥ 2), Claude categorises every previous validated topic into one of three buckets before suggesting new ones:

| Bucket | Condition | Action |
|---|---|---|
| **Followed-up** | Topic was open/in-progress last call AND discussed this call | Status updated, new summary + follow-ups written |
| **Not discussed** | Topic was open/in-progress last call AND not mentioned this call | Status unchanged, flagged for user acknowledgement |
| **New** | Topic has no prior record in this project | Fresh entry with `first_raised_call_id = current_call` |

**Not-discussed gate:** before `POST /validate` is accepted, all topics in the "not discussed" bucket must have a disposition set by the user (update status, archive, or explicitly keep as-is). Skipping is not allowed — the API returns 422 with `{"error": "unacknowledged_topics", "ids": [...]}` if any remain.

**Staleness counter (`calls_open`):** incremented by 1 each time a topic exits extraction still `open` or `in_progress`. Reset to 0 when status becomes `resolved`.

---

## Pre-call brief

`GET /api/calls/{call_id}/brief` — generated before a call starts (Topics stage not yet reached).

Claude receives:
- All open/in-progress topics from previous calls (with `calls_open` and `sentiment`)
- Their most-recent `follow_up_items` and `decisions`

Returns a short structured brief:
```json
{
  "priority_topics": [...],   // open topics sorted by calls_open desc, concern first
  "decisions_to_confirm": [...],  // decisions from last call worth confirming
  "watch_list": [...]         // topics with sentiment=concern
}
```

Brief is read-only — it does not create or modify any topic rows.

---

## Acceptance Criteria
- [ ] `POST /api/calls/{call_id}/topics/extract` triggers Claude extraction (only when explicitly called — NFR-08)
  - Call 1: extracts fresh from transcript + artifact contents → returns `{name, summary, follow_up_items, decisions, status, owner, sentiment}` list
  - Call 2+: fetches validated topics from previous Done calls, groups them into three buckets (followed-up / not-discussed / new), returns all three groups for UI review
  - Uses `claude-sonnet-4-6`
- [ ] `POST /api/calls/{call_id}/topics` saves the user-validated topic list:
  - New topics → inserted into `topics` table with `first_raised_call_id`
  - Updates to existing topics → new row in `topic_updates` table; `calls_open` incremented if still open/in_progress, reset if resolved
  - Archived topics → `archived = true`, excluded from future extraction context
- [ ] `POST /api/calls/{call_id}/topics/validate` advances `kanban_stage` to `'done'`
  - Returns 422 if no topics exist for this call
  - Returns 422 with `{"error": "unacknowledged_topics", "ids": [...]}` if any not-discussed topics have no disposition
- [ ] `GET /api/calls/{call_id}/brief` returns pre-call brief (priority_topics, decisions_to_confirm, watch_list) — Call 1 returns empty brief gracefully
- [ ] `GET /api/projects/{project_id}/topics` returns all non-archived topics with full update history (for Topics Dashboard)
- [ ] All Claude calls logged via `claude_logger`

## Tasks
- [ ] **Check DB schema** — verify `topics` + `topic_updates` tables have all 9 fields (add migration for `decisions`, `calls_open`, `archived` if missing)
- [ ] Create `backend/services/topics_service.py`:
  - `extract_topics(call_id) → {followed_up, not_discussed, new_topics}`
  - `get_previous_topics(project_id, exclude_call_id) → list`
  - `generate_brief(call_id) → brief`
  - `increment_staleness(topic_ids)` / `reset_staleness(topic_id)`
- [ ] Create `backend/routers/topics.py` — POST /extract, POST / (save), POST /validate, GET /brief, GET (dashboard)
- [ ] Register router in `backend/main.py`
- [ ] Write tests: `backend/tests/test_topics.py` (mock Claude)

## Dev Tests
- `backend/tests/test_topics.py`:
  - `POST /extract` Call 1 → Claude called with transcript + artifacts, returns all 9 fields (mocked)
  - `POST /extract` Call 2 → returns three buckets; not-discussed bucket populated when prior topic absent from transcript
  - `POST /` (save topics) → topic rows + topic_update rows created; `calls_open` incremented for open/in-progress, reset for resolved
  - `POST /validate` with all topics acknowledged → call advances to `'done'`
  - `POST /validate` with no topics → 422
  - `POST /validate` with unacknowledged not-discussed topics → 422 with `unacknowledged_topics`
  - `GET /brief` Call 1 → returns empty brief (no prior topics)
  - `GET /brief` Call 2+ → returns priority_topics sorted by `calls_open` desc, concern-first
