# Story 5.4 — Artifacts Stage UI

**Epic:** EPIC-5 — Artifacts Stage
**Maps to plan:** Slice 5
**Maps to PRD:** US-03, US-04, US-05, FR-06, FR-07, NFR-08
**Status:** `done`
**Depends on:** Story 5.3

---

## Goal
The Artifacts stage in the call workflow shows all artifact types. User selects which ones to run (Claude / Manual / Skip), triggers generation, watches live progress via SSE, edits content, and marks each Done. Stage cannot advance until all included artifacts are Done.

## Acceptance Criteria
- [x] `ArtifactSelector` shows all artifact types with 3 options per row: "Generate via Claude" · "Manual" · "Skip"
- [x] "Generate" button is enabled only after at least one artifact is set (not all skipped)
- [x] NFR-08: no API call fires until user clicks "Generate"
- [x] Clicking "Generate" calls `POST /api/calls/{id}/artifacts` then opens SSE stream to `/api/calls/{id}/artifacts/stream`
- [x] Each `ArtifactCard` shows live status: `pending` (grey) · `generating` (spinner) · `done` (green) · `error` (red with retry)
- [x] Manual artifacts show an empty editable textarea immediately — no spinner
- [x] All artifact content is editable inline (both Claude-generated and manual)
- [x] "Mark Done" button per artifact — turns card green
- [x] "Proceed to Topics" button appears only when all included (non-skipped) artifacts are marked Done
- [x] Clicking "Proceed to Topics" calls `PATCH /api/calls/{id}/stage` to advance to `'topics'`
- [x] All SSE events logged via `logger`

## Tasks
- [x] Create `frontend/src/components/ArtifactSelector.tsx` — per-type mode selector
- [x] Create `frontend/src/components/ArtifactCard.tsx` — status badge, editable content, Mark Done button
- [x] Create `frontend/src/components/ArtifactsStage.tsx` — orchestrates selector, generation, cards
- [x] Wire SSE: dedicated `/api/sse/[...path]/route.ts` proxy streams body without buffering
- [x] Manage state: selections → artifact rows → status per artifact
- [x] "Proceed" button: enabled only when all non-skipped artifacts have `status === 'done'`
- [x] Inline edit: `PATCH /api/artifacts/{id}` with updated content on Mark Done

## Dev Tests
Verify manually:
- Select 3 Claude + 2 Manual + 1 Skip → click Generate
- Manual cards show editable textarea immediately
- Claude cards show spinner → content appears as SSE events arrive
- Edit a generated artifact → content updates
- Mark each Done → "Proceed" button becomes active
- Click Proceed → call advances to Topics stage
