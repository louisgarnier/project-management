# Server Control — Design Spec

**Date:** 2026-04-09
**Feature:** Start/stop the local transcription server from within the app
**Status:** Approved

---

## Problem

The transcription server (`uvicorn` on port 8001) must be started manually from the terminal. This is unacceptable UX. The user needs a button in the app to start and stop it.

## Constraint

A browser cannot spawn OS processes. Something already running must receive the "start" command. The Next.js dev server is already running locally — we use it.

---

## Architecture

### New: Local control API (Next.js server-side routes)

Three route handlers added to the Next.js app. These are **not** proxied to Railway — they run on the local Node.js process.

| Route | Method | Action |
|---|---|---|
| `/api/local/start` | POST | Spawns `./run_transcription.sh`, stores process reference |
| `/api/local/stop` | POST | Kills the stored process |
| `/api/local/status` | GET | Returns `{ running: boolean }` |

**Process tracking:** A module-level singleton in `frontend/app/api/local/process.ts` holds the `ChildProcess` reference. Works correctly in `npm run dev` (single Node.js process). If Next.js restarts, the reference is lost — the transcription server may still be running, so `/api/local/status` falls back to a health check against `localhost:8001`.

**Working directory:** Routes use `process.cwd()` which is the project root when `npm run dev` is run from the project root. The script path is `./run_transcription.sh`.

**No Railway involvement:** These routes live at `/api/local/` — the proxy at `/api/proxy/` only forwards paths that start with `/api/proxy/`. No collision.

### Modified: `TranscriptionStatusBadge`

Extended to include start/stop controls. States:

| State | Badge | Button |
|---|---|---|
| `unknown` (initial) | — (null) | — |
| `offline` | Orange "Server offline" | "Start server" button |
| `starting` | Grey "Starting…" + spinner | — |
| `online` | Green "Server online" | "Stop server" button |
| `stopping` | Grey "Stopping…" | — |

The badge polls `GET /api/local/status` every 5 seconds (replaces the current direct health check to `localhost:8001`). The local status route checks both the stored process reference and the health endpoint.

### Removed: `OfflineModal`

The OfflineModal (which showed terminal instructions) is removed from `TranscriptStage`. Now that the user can start the server from the badge, the modal is obsolete.

---

## File Map

| File | Action |
|---|---|
| `frontend/app/api/local/process.ts` | Create — module singleton holding `ChildProcess` reference |
| `frontend/app/api/local/start/route.ts` | Create — POST handler, spawns script |
| `frontend/app/api/local/stop/route.ts` | Create — POST handler, kills process |
| `frontend/app/api/local/status/route.ts` | Create — GET handler, returns running state |
| `frontend/src/components/TranscriptionStatusBadge.tsx` | Modify — add start/stop button, new states |
| `frontend/src/components/TranscriptStage.tsx` | Modify — remove OfflineModal import and usage |
| `frontend/src/components/OfflineModal.tsx` | Delete |

---

## Acceptance Criteria

- [ ] "Start server" button visible when server is offline on the transcript stage page
- [ ] Clicking "Start server" → badge shows "Starting…" → transitions to "Server online" once health check passes
- [ ] "Stop server" button visible when server is online
- [ ] Clicking "Stop server" → kills the transcription process → badge shows "Server offline"
- [ ] If the transcription server was already running before the app loaded, badge correctly shows "Server online"
- [ ] No terminal required at any point after initial `npm run dev`
- [ ] All state transitions logged via `logger`

---

## Out of Scope

- Starting the server from pages other than the transcript stage
- Auto-starting the server on app load
- Production deployment (this feature is local-only by design)
