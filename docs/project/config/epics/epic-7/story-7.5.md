# Story 7.5 — Project Topics UI (project_topics stage)

**Epic:** EPIC-7 — Two-Step Topic Extraction
**Status:** `pending`

---

## Goal
New `ProjectTopicsStage` component handles the `project_topics` stage. Shows the 3-bucket result from Step 2 aggregation. User can manually link a misclassified "new" topic to an existing project topic. On validate, topics are saved and stage advances to artifacts.

## Acceptance Criteria
- [ ] `ProjectTopicsStage` shown when `call.kanban_stage === "project_topics"`
- [ ] On mount: if aggregation result not in state (user navigated away), re-runs Step 1 silently then triggers Step 2 automatically
- [ ] Shows 3 buckets: Followed Up / Not Discussed / New Topics
- [ ] Each card fully editable (same as current TopicsStage)
- [ ] **"Link to existing" on New Topic cards:** button opens searchable dropdown of existing project topics; selecting moves card to Followed Up bucket with matched `topic_id`
- [ ] Not Discussed topics require disposition (keep / archive) before validate is enabled
- [ ] Validate calls `POST /calls/{id}/topics` (save) then `POST /calls/{id}/topics/validate`
- [ ] Validate success → stage advances to `artifacts`
- [ ] `call.is_locked` respected: editing disabled when locked

## Tasks
- [ ] Create `frontend/src/components/ProjectTopicsStage.tsx`
- [ ] Add `topicsAPI.listForProject` used for "Link to existing" picker (already exists)
- [ ] Wire into `frontend/app/projects/[id]/calls/[call_id]/page.tsx` for `project_topics` stage
- [ ] Remove old `TopicsStage` reference from `call_topics` routing (TopicsStage now only used for historical view)

## Dev Tests
- Manual: arrive at project_topics → 3 buckets shown
- Manual: "Link to existing" → dropdown appears, select topic → card moves to Followed Up
- Manual: validate without dispositions → button disabled
- Manual: validate with all dispositions → advances to artifacts
