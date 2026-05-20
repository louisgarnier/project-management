# Story 4.8 — Kanban History Trail + Persistent Transcript Panel

**Epic:** EPIC-4 — Transcript Stage
**Status:** `done`
**Depends on:** Story 4.5

---

## Goal
Each Kanban column becomes a history trail. A call appears in every column it has passed through, not just its current stage. Active cards (currently at that stage) look distinct from historical cards (already past that stage). Clicking any card in Get Transcript opens the transcript for viewing/editing.

## Context
Currently a call disappears from "Get Transcript" when it advances to Artifacts. The user loses all traceability of what happened at each stage. This story fixes that by making the board a cumulative progress view.

## What Changes

| Stage reached | Get Transcript | Artifacts | Topics | Done |
|---|---|---|---|---|
| transcript | ✅ active | — | — | — |
| artifacts | ✅ historical | ✅ active | — | — |
| topics | ✅ historical | ✅ historical | ✅ active | — |
| done | ✅ historical | ✅ historical | ✅ historical | ✅ active |

**Active card** = call is currently at this stage → current white card styling
**Historical card** = call has passed this stage → muted `bg-[#f4f5f7]` background, faded left border, small "✓" label

## Acceptance Criteria

### KanbanBoard.tsx
- [x] Column filter changed from `c.kanban_stage === col.key` to `STAGE_ORDER.indexOf(c.kanban_stage) >= STAGE_ORDER.indexOf(col.key)`
- [x] Each `CallCard` receives `isHistorical={call.kanban_stage !== col.key}` prop
- [x] Column count badge counts all cards in that column (active + historical)

### CallCard.tsx
- [x] Accepts `isHistorical?: boolean` prop
- [x] Historical card: `bg-[#f4f5f7]` background (vs white for active), left border color at 40% opacity, small "✓ done" label in top-right
- [x] Active card: styling unchanged from current
- [x] Both active and historical cards remain clickable

### Call detail page — Persistent Transcript Panel
- [x] At all stages **after** transcript (artifacts, topics, done): a collapsible "Transcript" section shown below the main stage content
- [x] Panel shows the saved transcript text in an editable textarea
- [x] "Save changes" button calls `PATCH /api/calls/{id}/transcript` — no stage change
- [x] Unsaved changes indicator (button enabled only when text differs from saved)
- [x] "↓ Download .txt" link in the panel footer
- [x] Panel is collapsed by default, expanded on click (to keep the UI clean)

### Clicking a historical card in Get Transcript
- [x] Navigates to call detail page (same as active card)
- [x] The transcript panel is visible and editable

## Tasks
- [x] Update `KanbanBoard.tsx` — column filtering + pass `isHistorical` to CallCard
- [x] Update `CallCard.tsx` — `isHistorical` prop + visual differentiation
- [x] Add `TranscriptPanel.tsx` — collapsible transcript viewer/editor (PATCH save, download)
- [x] Wire `TranscriptPanel` into call detail page for stages: artifacts, topics, done
- [x] Verify lint passes, no TypeScript errors
- [x] Update `codebase.md` and close story
