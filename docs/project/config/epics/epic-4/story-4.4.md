# Story 4.4 — Server Control UI

**Epic:** EPIC-4 — Transcript Stage
**Status:** `in progress`
**Priority:** Blocker — Transcript Stage is unusable without this

---

## Goal
The user can start and stop the local transcription server directly from the app. No terminal required at any point.

## Acceptance Criteria
- [ ] Transcript stage badge shows "Server offline" + "Start server" button when server is not running
- [ ] Clicking "Start server" → badge shows "Starting…" → transitions to "Server online" once health check passes
- [ ] Transcript stage badge shows "Server online" + "Stop" button when server is running
- [ ] Clicking "Stop" → kills the process → badge shows "Server offline"
- [ ] If server was already running before the app loaded, badge correctly shows "Server online"
- [ ] Selecting MP3 while offline shows inline error "Server is offline. Use the Start server button above." — no modal
- [ ] OfflineModal deleted
- [ ] No terminal required at any point after initial `npm run dev`
- [ ] All state transitions logged

## Tasks
- [ ] Create `/api/local/` Next.js route handlers (start, stop, status) + process singleton
- [ ] Add `localServerAPI` to `frontend/src/api/client.ts`
- [ ] Replace `TranscriptionStatusBadge` with stateful start/stop version
- [ ] Update `TranscriptStage` — remove OfflineModal, inline error on offline MP3
- [ ] Delete `OfflineModal.tsx`

## Plan
`docs/project/config/2026-04-09-server-control-plan.md`
