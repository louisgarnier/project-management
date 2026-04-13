# Story 7.1 — DB Migration: New Kanban Stages

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `pending`

---

## Goal
Replace the single `topics` kanban stage with two stages: `call_topics` (Step 1 — extract from this call only) and `project_topics` (Step 2 — match against accumulated project topics). Update all DB constraints, backend stage ordering, and frontend type definitions.

## Acceptance Criteria
- [ ] Migration `011_two_step_topics_stages.sql` updates CHECK constraint to `('transcript','call_topics','project_topics','artifacts','done')`
- [ ] All existing rows at `topics` stage migrated to `call_topics`
- [ ] Backend `STAGE_ORDER` updated in `calls.py`
- [ ] `KanbanStage` TypeScript type updated
- [ ] `STAGES` array and `getCellState` in `KanbanBoard.tsx` updated (5 columns)
- [ ] All backend tests pass after migration

## Tasks
- [ ] Write `backend/database/migrations/011_two_step_topics_stages.sql`
- [ ] Update `STAGE_ORDER` in `backend/routers/calls.py`
- [ ] Update `KanbanStage` type in `frontend/src/types/index.ts`
- [ ] Update `STAGES` + `STAGE_ORDER` + `getCellState` in `frontend/src/components/KanbanBoard.tsx`
- [ ] Update `frontend/app/projects/[id]/calls/[call_id]/page.tsx` stage routing

## Dev Tests
- `backend/tests/test_calls.py` — all existing tests pass (no `topics` stage referenced)
- `npx tsc --noEmit` — 0 errors
