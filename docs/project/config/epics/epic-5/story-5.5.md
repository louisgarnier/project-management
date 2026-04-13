# Story 5.5 — Kanban Row-Per-Call Redesign

**Epic:** EPIC-5 — Artifacts Stage
**Design spec:** `docs/project/config/2026-04-13-kanban-row-per-call-design.md`
**Status:** `pending`

---

## Goal

Replace the 4-column stage-first Kanban board with a row-per-call layout. Each call is one horizontal row; the four stages (Transcript → Artifacts → Topics → Done) are read left to right.

## Acceptance Criteria

- [ ] Kanban board displays one row per call, ordered oldest to newest
- [ ] Each row shows call number, title, and date on the left (132px column)
- [ ] Each row has 4 stage cells: Transcript, Artifacts, Topics, Done
- [ ] Stage cell states: `done` (green), `active` (blue border), `pending` (gray dashed), `locked` (blue dashed, 🔒, 0.7 opacity)
- [ ] Transcript cell is never locked
- [ ] Artifacts and Topics cells are locked when the previous call has not reached `kanban_stage === 'done'`
- [ ] Clicking an `active` cell navigates to `/projects/:id/calls/:call_id`
- [ ] Clicking a `done` cell navigates to `/projects/:id/calls/:call_id?view=<stage>`
- [ ] Clicking a `pending` or `locked` cell does nothing
- [ ] "Add new call" button appears below all rows
- [ ] No backend changes — only `KanbanBoard.tsx` is modified

## Tasks

- [ ] Rewrite `frontend/src/components/KanbanBoard.tsx` — row-per-call layout
- [ ] ESLint passes with 0 errors

## Dev Tests

Manual browser verification:
- Project with 1 call in `transcript` stage → 1 row, Transcript active, all others pending (no locking since no previous call)
- Project with Call 1 done, Call 2 in `artifacts` → Call 2 Artifacts active, Topics pending; Call 3 (if exists) Artifacts + Topics locked
- Clicking done cell opens historical view
- Clicking locked cell does nothing
