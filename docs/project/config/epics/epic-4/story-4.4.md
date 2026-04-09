# Story 4.4 — Server Control UI

**Epic:** EPIC-4 — Transcript Stage
**Status:** `done`
**Priority:** Blocker — Transcript Stage is unusable without this

---

## Goal
The user can start and stop the local transcription server directly from the app. No terminal required at any point.

## Acceptance Criteria
- [x] Transcript stage badge shows "Server offline" + "Start server" button when server is not running
- [x] Clicking "Start server" → badge shows "Starting…" → transitions to "Server online" once health check passes
- [x] Transcript stage badge shows "Server online" + "Stop" button when server is running
- [x] Clicking "Stop" → kills the process → badge shows "Server offline"
- [x] If server was already running before the app loaded, badge correctly shows "Server online"
- [x] Selecting MP3 while offline shows inline error "Server is offline. Use the Start server button above." — no modal
- [x] OfflineModal deleted
- [x] No terminal required at any point after initial `npm run dev`
- [x] All state transitions logged

## Tasks
- [x] Create `/api/local/` Next.js route handlers (start, stop, status) + process singleton
- [x] Add `localServerAPI` to `frontend/src/api/client.ts`
- [x] Replace `TranscriptionStatusBadge` with stateful start/stop version
- [x] Update `TranscriptStage` — remove OfflineModal, inline error on offline MP3
- [x] Delete `OfflineModal.tsx`

## Plan
`docs/project/config/2026-04-09-server-control-plan.md`
