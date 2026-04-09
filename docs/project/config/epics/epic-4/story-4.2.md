# Story 4.2 — Transcript Stage Backend

**Epic:** EPIC-4 — Transcript Stage
**Maps to plan:** Slice 4
**Maps to PRD:** US-02, FR-02, FR-02b
**Status:** `done`

---

## Goal
Railway FastAPI receives transcripts (either from the local transcription server or direct .txt upload) and stores them in Supabase. The call card advances to `'artifacts'` stage automatically after storage.

## Acceptance Criteria
- [ ] `POST /api/calls/{call_id}/transcript` accepts a transcript text body and stores it in `calls.transcript`
- [ ] After storing, `kanban_stage` is automatically advanced to `'artifacts'`
- [ ] The endpoint is called by the Next.js proxy after either transcription or .txt upload
- [ ] 404 returned if call does not exist
- [ ] 409 returned if call is already past the `'transcript'` stage (duplicate submission guard)
- [ ] Transcript stored as plain text — never truncated
- [ ] All operations logged

## Tasks
- [x] Add `POST /api/calls/{call_id}/transcript` to `backend/routers/calls.py`
- [x] Update call row: set `transcript`, set `kanban_stage = 'artifacts'`
- [x] Add guard: reject if `kanban_stage != 'transcript'`
- [x] Write tests: `backend/tests/test_transcript.py`

## Dev Tests
- `backend/tests/test_transcript.py`:
  - `POST /transcript` with valid text → 200, call `kanban_stage` becomes `'artifacts'`
  - `POST /transcript` on a call already in `'artifacts'` stage → 409
  - `POST /transcript` on non-existent call → 404
  - Verify transcript stored in DB matches input exactly
