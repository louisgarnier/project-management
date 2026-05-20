# Story 4.5 — Transcript Review, Edit & Download

**Epic:** EPIC-4 — Transcript Stage
**Status:** `done`
**Priority:** Blocker — Get Transcript stage is incomplete without review/edit step

---

## Goal
After MP3 transcription or .txt upload, the user sees the full transcript in an editable textarea before it is saved. They can edit the text, download it, replace it entirely, or confirm and advance. The Kanban card also shows transcript metadata once the transcript is saved.

## Acceptance Criteria

### Backend
- [x] `calls` table: add `transcript_source TEXT` column (nullable) — stores source filename ("interview.mp3", "notes.txt")
- [x] `POST /api/calls/{call_id}/transcript` accepts optional `source_filename` field, stores in `transcript_source`
- [x] `PATCH /api/calls/{call_id}/transcript` — updates `transcript` text only, no stage change (for in-place edits after save)
  - 404 if call not found
  - 409 if call is at `transcript` stage (must use POST to save + advance)
  - Returns updated call
- [x] All new endpoints logged and tested (404, 409, happy path)

### Frontend — Transcript Review Screen
Shown after MP3 transcription completes OR after .txt upload (replaces auto-advance behaviour)

- [x] Source filename displayed: "From: interview.mp3" or "From: notes.txt"
- [x] Full transcript shown in an editable `<textarea>` (scrollable, monospace font)
- [x] Elapsed time shown during transcription
- [x] "Download .txt" button: downloads current textarea content as `transcript_[call-title].txt`
- [x] "Replace" button: clears local state, returns to upload step — no DB write
- [x] "Save & continue →" button: POSTs transcript + source_filename to backend → advances card to Artifacts
- [x] While saving: button shows "Saving…", disabled
- [x] Error state if save fails: inline error, stay on review screen

### Frontend — Kanban Card
- [x] `CallCard` for calls past `transcript` stage shows:
  - Transcript line count ("42 lines")
  - Source filename if available ("From: interview.mp3")
- [x] `CallCard` at `transcript` stage shows "No transcript yet"

## Tasks
- [x] Supabase migration: add `transcript_source` column to `calls` table
- [x] Backend: update `POST /api/calls/{id}/transcript` to accept + store `source_filename`
- [x] Backend: add `PATCH /api/calls/{id}/transcript` endpoint
- [x] Backend tests: PATCH 404, PATCH 409, PATCH happy path, POST with source_filename
- [x] Frontend: update `TranscriptStage.tsx` — after transcription/upload, show review screen instead of auto-advancing
- [x] Frontend: `callsAPI.updateTranscript(callId, transcript)` in `client.ts`
- [x] Frontend: update `CallCard.tsx` — show transcript metadata
