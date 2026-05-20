# Story 5.0 — Transcript Review & Redo

**Epic:** EPIC-5 — Artifacts Stage
**Status:** `done`
**Completed in:** EPIC-4 (session 2026-04-10)
**Priority:** First story in EPIC-5 — must be built before any artifact generation

---

## Goal
When a call card enters the Artifacts stage, the user sees the full transcript on the call detail page and can validate it before generating artifacts. If the transcript is wrong, a "Redo transcript" button clears it and sends the card back to the Get Transcript column.

## Acceptance Criteria
- [x] Artifacts stage call detail page shows the full transcript text in a read-only textarea
  - Implemented via `TranscriptPanel.tsx` — collapsible, editable, shown on all post-transcript stages
- [x] "Redo transcript" button visible on the Artifacts stage detail page
  - Implemented as "↩ Reset transcript" link on call detail page when `kanban_stage === "artifacts"`
  - Also available from the historical "Get Transcript" tile view
- [x] Clicking "Redo transcript" → confirmation dialog → clears `calls.transcript`, resets `kanban_stage` to `'transcript'`
- [x] After redo: card moves back to "Get Transcript" column on the kanban board
- [x] Backend: `DELETE /api/calls/{call_id}/transcript` — clears transcript, resets stage to `transcript`
  - 404 if call not found
  - 409 if call is NOT at `artifacts` stage
- [x] All operations logged

## Tasks
- [x] Add `DELETE /api/calls/{call_id}/transcript` to `backend/routers/calls.py`
- [x] Tests: 404, 409, happy path (stage resets to transcript, transcript cleared)
- [x] Artifacts stage UI on call detail page: transcript panel + "↩ Reset transcript" button + confirmation dialog

## Notes
Built as part of EPIC-4 extras. The `DELETE /api/calls/{call_id}/transcript` endpoint bypasses supabase-py's None-filtering bug by using `client.postgrest.session.patch()` with explicit `json.dumps()` to guarantee NULL is written to DB. See ADR-002 for the known gotcha.
