# Story 4.3 — Transcript Stage UI

**Epic:** EPIC-4 — Transcript Stage
**Maps to plan:** Slice 4
**Maps to PRD:** US-02, FR-02b, FR-02c, NFR-08
**Status:** `done`

---

## Goal
The call detail page shows the Transcript stage UI. User picks MP3 (triggers local transcription) or drops a .txt (direct). A persistent status badge shows whether the local transcription server is online. If offline and user tries to upload MP3, a modal shows how to start the server.

## Acceptance Criteria
- [x] Call detail page (`/projects/[id]/calls/[call_id]`) shows the correct stage component based on `kanban_stage`
- [x] At `'transcript'` stage: file picker accepts `.mp3` or `.txt` only
- [x] `TranscriptionStatusBadge` shows `Online ✅` or `Offline ⚠️`, pings `localhost:8001/health` every 30 seconds
- [x] If user selects MP3 and server is **online**: file sent to `localhost:8001/transcribe`, transcript returned, then sent to Railway `POST /api/calls/{id}/transcript`
- [x] If user selects MP3 and server is **offline**: `OfflineModal` opens immediately — no API call made
- [x] `OfflineModal` shows exact steps: (1) open terminal, (2) navigate to Call Tracker folder, (3) run `./run_transcription.sh`. Dismisses automatically when server comes back online.
- [x] If user selects `.txt`: file content read in browser, sent directly to Railway `POST /api/calls/{id}/transcript` — local server not involved
- [x] After transcript stored, call card advances to Artifacts stage and UI updates
- [x] NFR-08 respected: no API call fires until user explicitly selects a file
- [x] All steps logged via `logger`

## Tasks
- [x] Create `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — stage router (renders correct stage component)
- [x] Create `frontend/components/TranscriptionStatusBadge.tsx` — polls `localhost:8001/health`, shows Online/Offline
- [x] Create `frontend/components/TranscriptStage.tsx` — file picker, handles MP3 vs .txt logic
- [x] Create `frontend/components/OfflineModal.tsx` — startup instructions, auto-dismiss on server online
- [x] Wire badge polling: `setInterval` every 30s, update state
- [x] Wire OfflineModal: poll `localhost:8001/health` inside modal, dismiss when online

## Dev Tests
Verify manually with both local transcription server running and stopped:
- Server online: upload MP3 → transcript appears in textarea, card advances to Artifacts
- Server online: upload .txt → transcript stored, card advances
- Server offline: upload MP3 → OfflineModal opens, no transcription call made
- OfflineModal: start server → modal auto-dismisses
- Badge updates within 30s of server coming online/offline
