# Story 7.4 — Call Topics UI (call_topics stage)

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `pending`

---

## Goal
New `CallTopicsStage` component handles the `call_topics` kanban stage. User extracts this call's topics unbiased, reviews/edits them, then continues — which triggers Step 2 aggregation and advances the stage.

## Acceptance Criteria
- [ ] `CallTopicsStage` shown when `call.kanban_stage === "call_topics"`
- [ ] "Extract this call's topics" button calls `POST /extract_call`
- [ ] Flat list of editable topic cards (name, summary, follow_ups, status, owner, sentiment)
- [ ] "Continue →" button sends edited topics to `POST /aggregate`
- [ ] **Call 1 auto-advance:** backend returns `auto_advanced: true` → show brief "Topics saved as project baseline" toast → reload call → UI shows artifacts stage
- [ ] **Call 2+:** stage advances to `project_topics` → UI shows `ProjectTopicsStage`
- [ ] Loading and error states for both API calls
- [ ] `frontend/src/api/client.ts` has `topicsAPI.extractCall(callId)` and `topicsAPI.aggregate(callId, topics)`

## Tasks
- [ ] Add `extractCall` and `aggregate` to `topicsAPI` in `frontend/src/api/client.ts`
- [ ] Create `frontend/src/components/CallTopicsStage.tsx`
- [ ] Wire into `frontend/app/projects/[id]/calls/[call_id]/page.tsx` for `call_topics` stage

## Dev Tests
- Manual: extract on a call with transcript → flat list appears, fields editable
- Manual: Call 1 → continue → auto-advances to artifacts
- Manual: Call 2+ → continue → shows ProjectTopicsStage
