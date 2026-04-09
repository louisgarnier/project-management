# Story 4.3 — Transcript Stage UI

**Epic:** EPIC-4 — Transcript Stage
**Maps to plan:** Slice 4
**Maps to PRD:** US-02, FR-02b, FR-02c, NFR-08
**Status:** `pending`

---

## Goal
The call detail page shows the Transcript stage UI. User picks MP3 (triggers local transcription) or drops a .txt (direct). A persistent status badge shows whether the local transcription server is online. If offline and user tries to upload MP3, a modal shows how to start the server.

## Acceptance Criteria
- [ ] Call detail page (`/projects/[id]/calls/[call_id]`) shows the correct stage component based on `kanban_stage`
- [ ] At `'transcript'` stage: file picker accepts `.mp3` or `.txt` only
- [ ] `TranscriptionStatusBadge` shows `Online ✅` or `Offline ⚠️`, pings `localhost:8001/health` every 30 seconds
- [ ] If user selects MP3 and server is **online**: file sent to `localhost:8001/transcribe`, transcript returned, then sent to Railway `POST /api/calls/{id}/transcript`
- [ ] If user selects MP3 and server is **offline**: `OfflineModal` opens immediately — no API call made
- [ ] `OfflineModal` shows exact steps: (1) open terminal, (2) navigate to Call Tracker folder, (3) run `./run_transcription.sh`. Dismisses automatically when server comes back online.
- [ ] If user selects `.txt`: file content read in browser, sent directly to Railway `POST /api/calls/{id}/transcript` — local server not involved
- [ ] After transcript stored, call card advances to Artifacts stage and UI updates
- [ ] NFR-08 respected: no API call fires until user explicitly selects a file
- [ ] All steps logged via `logger`

## Tasks
- [ ] Create `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — stage router (renders correct stage component)
- [ ] Create `frontend/components/TranscriptionStatusBadge.tsx` — polls `localhost:8001/health`, shows Online/Offline
- [ ] Create `frontend/components/TranscriptStage.tsx` — file picker, handles MP3 vs .txt logic
- [ ] Create `frontend/components/OfflineModal.tsx` — startup instructions, auto-dismiss on server online
- [ ] Wire badge polling: `setInterval` every 30s, update state
- [ ] Wire OfflineModal: poll `localhost:8001/health` inside modal, dismiss when online

## Dev Tests
Verify manually with both local transcription server running and stopped:
- Server online: upload MP3 → transcript appears in textarea, card advances to Artifacts
- Server online: upload .txt → transcript stored, card advances
- Server offline: upload MP3 → OfflineModal opens, no transcription call made
- OfflineModal: start server → modal auto-dismisses
- Badge updates within 30s of server coming online/offline
