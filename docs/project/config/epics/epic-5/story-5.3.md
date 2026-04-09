# Story 5.3 — Artifacts Stage UI

**Epic:** EPIC-5 — Artifacts Stage
**Maps to plan:** Slice 5
**Maps to PRD:** US-03, US-04, US-05, FR-06, FR-07, NFR-08
**Status:** `pending`

---

## Goal
The Artifacts stage shows all 6 artifact types. User sets each to Claude / Manual / Skip, triggers generation, watches live progress via SSE, edits content, and marks each Done. Stage cannot advance until all included artifacts are Done.

## Acceptance Criteria
- [ ] `ArtifactSelector` shows all artifact types with 3 options per row: "Generate via Claude" · "Manual" · "Skip"
- [ ] "Generate" button is enabled only after at least one artifact is set (not all skipped)
- [ ] NFR-08: no API call fires until user clicks "Generate"
- [ ] Clicking "Generate" calls `POST /api/calls/{id}/artifacts` then opens SSE stream to `/api/calls/{id}/artifacts/stream`
- [ ] Each `ArtifactCard` shows live status: `pending` (grey) · `generating` (spinner) · `done` (green) · `error` (red with retry)
- [ ] Manual artifacts show an empty editable textarea immediately — no spinner
- [ ] All artifact content is editable inline (both Claude-generated and manual)
- [ ] "Mark Done" button per artifact — turns card green
- [ ] "Proceed to Topics" button appears only when all included (non-skipped) artifacts are marked Done
- [ ] Clicking "Proceed to Topics" calls `PATCH /api/calls/{id}/stage` to advance to `'topics'`
- [ ] All SSE events logged via `logger.sse`

## Tasks
- [ ] Create `frontend/components/ArtifactSelector.tsx` — per-type mode selector
- [ ] Create `frontend/components/ArtifactCard.tsx` — status badge, editable content, Mark Done button
- [ ] Create `frontend/components/ArtifactsStage.tsx` — orchestrates selector, generation, cards
- [ ] Wire SSE: `EventSource` on `/api/proxy/calls/{id}/artifacts/stream`
- [ ] Manage state: selections → artifact rows → status per artifact
- [ ] "Proceed" button: enabled only when `artifacts.filter(not skipped).every(a => a.status === 'done')`
- [ ] Inline edit: `PATCH /api/artifacts/{id}` with updated content on blur

## Dev Tests
Verify manually:
- Select 3 Claude + 2 Manual + 1 Skip → click Generate
- Manual cards show editable textarea immediately
- Claude cards show spinner → then content as SSE events arrive
- Edit a generated artifact → content updates
- Mark each Done → "Proceed" button becomes active
- Click Proceed → call advances to Topics stage
