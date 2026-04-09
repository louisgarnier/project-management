# Story 3.2 — Kanban Board UI

**Epic:** EPIC-3 — Kanban Board & Calls
**Maps to plan:** Slice 3
**Maps to PRD:** US-07, FR-03
**Status:** `done`
**Design spec:** `docs/project/config/2026-04-09-story-3.2-kanban-board-design.md`
**Implementation plan:** `docs/project/config/2026-04-09-story-3.2-kanban-board-plan.md`

---

## Goal
`/projects/[id]` shows a 4-column kanban board with call cards. "New Call" button is disabled when an active call exists. User can click a call card to open it (placeholder detail view).

## Acceptance Criteria
- [x] Project page has two tabs: "Kanban" and "Topics" (Topics tab placeholder for now)
- [x] Kanban view shows 4 columns: Get Transcript · Artifacts · Topics · Done
- [x] Each call appears as a card in the correct column based on `kanban_stage`
- [x] "New Call" button opens a create form (title input)
- [x] "New Call" button is **disabled** (with tooltip) when any call is not `'done'`
- [x] Creating a new call calls `POST /api/projects/{id}/calls` and reloads the board
- [x] Clicking a card navigates to `/projects/[id]/calls/[call_id]` (placeholder for now)
- [x] Done calls show as read-only cards in the "Done" column

## Tasks
- [x] Update `frontend/app/projects/[id]/page.tsx` — fetch calls, render KanbanBoard + tabs
- [x] Create `frontend/components/KanbanBoard.tsx` — 4 columns, renders CallCard per call
- [x] Create `frontend/components/CallCard.tsx` — title, stage badge, click to navigate
- [x] Create `frontend/components/NewCallModal.tsx` — title input, POST on submit
- [x] Disable "New Call" if `calls.some(c => c.kanban_stage !== 'done')`
- [x] Create placeholder `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

## Dev Tests
Verify manually:
- Board loads with calls in correct columns
- "New Call" disabled when active call exists (try to click — confirm no API call fires)
- Create call → card appears in "Get Transcript" column
- Navigate to call detail → placeholder renders
