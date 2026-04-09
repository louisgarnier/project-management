# Story 5.0 — Transcript Review & Redo

**Epic:** EPIC-5 — Artifacts Stage
**Status:** `pending`
**Priority:** First story in EPIC-5 — must be built before any artifact generation

---

## Goal
When a call card enters the Artifacts stage, the user sees the full transcript on the call detail page and can validate it before generating artifacts. If the transcript is wrong, a "Redo transcript" button clears it and sends the card back to the Get Transcript column.

## Acceptance Criteria
- [ ] Artifacts stage call detail page shows the full transcript text in a read-only textarea
- [ ] "Redo transcript" button visible on the Artifacts stage detail page
- [ ] Clicking "Redo transcript" → confirmation dialog → clears `calls.transcript`, resets `kanban_stage` to `'transcript'`
- [ ] After redo: card moves back to "Get Transcript" column on the kanban board
- [ ] Backend: `DELETE /api/calls/{call_id}/transcript` — clears transcript, resets stage to `transcript`
  - 404 if call not found
  - 409 if call is NOT at `artifacts` stage (can only redo from artifacts)
- [ ] All operations logged

## Tasks
- [ ] Add `DELETE /api/calls/{call_id}/transcript` to `backend/routers/calls.py`
- [ ] Tests: 404, 409, happy path (stage resets to transcript, transcript cleared)
- [ ] Artifacts stage UI on call detail page: show transcript text + "Redo transcript" button + confirmation dialog
