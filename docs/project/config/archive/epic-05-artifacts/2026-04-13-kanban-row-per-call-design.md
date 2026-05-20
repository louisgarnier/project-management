# Kanban Row-Per-Call Redesign — Design Spec

## Goal

Replace the current 4-column stage-first Kanban board with a row-per-call layout where each call is one horizontal row and the four stages (Transcript → Artifacts → Topics → Done) are columns read left to right.

## Approved Mockup

`kanban-row-per-call.html` — approved 2026-04-13.

## Layout

```
                [Transcript]  [Artifacts]  [Topics]  [Done]
Call 1  Title   ✓ done        ✓ done       ✓ done    ✓ Closed
Call 2  Title   ✓ done        → in prog    upcoming  —
Call 3  Title   ✓ done        🔒 locked    🔒 locked  —
[+ Add new call]
```

- Left column (132px): call number, title, date — not clickable, informational only
- Four stage cells per row — each cell is clickable and navigates to that call's stage view
- Bottom row: "Add new call" button (full width of stage area, dashed border)

## Stage Cell States

| State | Trigger | Visual |
|---|---|---|
| `done` | Stage previously completed | Gray bg, green ✓ badge, ✓ checkmark icon |
| `active` | Call's current `kanban_stage` | White bg, blue border (1.5px) |
| `pending` | Stage not yet reached but unlocked | Gray bg, gray dashed border |
| `locked` | Artifacts/Topics and previous call not done | Gray bg, blue dashed border, 0.7 opacity, 🔒 |

A cell is **done** if the call has progressed past that stage (`STAGE_INDEX[call.kanban_stage] > STAGE_INDEX[cell]`).
A cell is **active** if `call.kanban_stage === cell.key`.
A cell is **pending** if stage not reached AND not locked.
A cell is **locked** if the stage is `artifacts` or `topics` AND the previous call in the project has not reached `done`.

## Dependency / Locking Rule

> Artifacts and Topics cells for Call N are locked until Call N-1's `kanban_stage === 'done'`.

- Transcript is **never locked** — you can always add a transcript to any call.
- Done cell is **never locked** — it becomes active once Topics is completed.
- The locking is purely a UI concern: the backend already enforces sequential ordering via `kanban_stage`.

## Navigation (click behaviour)

Clicking a stage cell opens the call at that stage:
- Active cell → `GET /projects/:id/calls/:call_id` (normal call page)
- Done cell → `GET /projects/:id/calls/:call_id?view=<stage>` (historical read view)
- Pending / locked cells → no navigation (cursor: default)

## Call ordering

Calls are displayed in creation order (oldest first, newest at bottom). The "Add new call" button always appears at the bottom.

## Component changes

| File | Change |
|---|---|
| `frontend/src/components/KanbanBoard.tsx` | Replace column layout with row-per-call layout |
| `frontend/src/components/CallCard.tsx` | No change — still used inside each stage cell |
| `frontend/app/projects/[id]/board/page.tsx` | No change — passes `calls` prop as before |

`KanbanBoard.tsx` is the only file that changes. The `calls` prop shape is unchanged.

## Out of scope

- No backend changes — all data already available via existing `GET /api/projects/:id/calls`
- No new API calls
- No sorting or filtering UI
- No drag-and-drop
