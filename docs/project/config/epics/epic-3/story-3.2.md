# Story 3.2 — Kanban Board UI

**Epic:** EPIC-3 — Kanban Board & Calls
**Maps to plan:** Slice 3
**Maps to PRD:** US-07, FR-03
**Status:** `in_progress`
**Design spec:** `docs/project/config/2026-04-09-story-3.2-kanban-board-design.md`
**Implementation plan:** `docs/project/config/2026-04-09-story-3.2-kanban-board-plan.md`

---

## Goal
`/projects/[id]` shows a 4-column kanban board with call cards. "New Call" button is disabled when an active call exists. User can click a call card to open it (placeholder detail view).

## Acceptance Criteria
- [ ] Project page has two tabs: "Kanban" and "Topics" (Topics tab placeholder for now)
- [ ] Kanban view shows 4 columns: Get Transcript · Artifacts · Topics · Done
- [ ] Each call appears as a card in the correct column based on `kanban_stage`
- [ ] "New Call" button opens a create form (title input)
- [ ] "New Call" button is **disabled** (with tooltip) when any call is not `'done'`
- [ ] Creating a new call calls `POST /api/projects/{id}/calls` and reloads the board
- [ ] Clicking a card navigates to `/projects/[id]/calls/[call_id]` (placeholder for now)
- [ ] Done calls show as read-only cards in the "Done" column

## Tasks
- [ ] Update `frontend/app/projects/[id]/page.tsx` — fetch calls, render KanbanBoard + tabs
- [ ] Create `frontend/components/KanbanBoard.tsx` — 4 columns, renders CallCard per call
- [ ] Create `frontend/components/CallCard.tsx` — title, stage badge, click to navigate
- [ ] Create `frontend/components/NewCallModal.tsx` — title input, POST on submit
- [ ] Disable "New Call" if `calls.some(c => c.kanban_stage !== 'done')`
- [ ] Create placeholder `frontend/app/projects/[id]/calls/[call_id]/page.tsx`

## Dev Tests
Verify manually:
- Board loads with calls in correct columns
- "New Call" disabled when active call exists (try to click — confirm no API call fires)
- Create call → card appears in "Get Transcript" column
- Navigate to call detail → placeholder renders
