# Story 6.2 — Topics Stage UI

**Epic:** EPIC-6 — Topics Stage
**Maps to plan:** Slice 6
**Maps to PRD:** US-06, FR-08, FR-09, NFR-08
**Status:** `pending`

---

## Goal
The Topics stage shows two choices: "Extract via Claude" or "Add Manually". User reviews/edits topics, then validates to move the call to Done.

## Acceptance Criteria
- [ ] Topics stage shows two clearly labelled options: "Extract via Claude" and "Add Manually"
- [ ] NFR-08: no API call fires until user explicitly clicks one of the two options
- [ ] If "Extract via Claude": spinner shows while extraction runs, then topic list appears for review/edit/add/remove
- [ ] If "Add Manually": empty topic list appears immediately, user adds topics via an "Add Topic" form
- [ ] Each topic shows: name (editable), summary (editable), follow-up items (editable list)
- [ ] User can add topics, remove topics, edit any field
- [ ] "Validate & Complete Call" button calls `POST /api/calls/{id}/topics` (save) then `POST /api/calls/{id}/topics/validate`
- [ ] After validation, call card moves to "Done" column on the kanban board
- [ ] Error state: if Claude extraction fails, show error with "Try Again" button

## Tasks
- [ ] Create `frontend/components/TopicsStage.tsx` — choice screen, then topic list
- [ ] Create `frontend/components/TopicEditor.tsx` — individual topic row (name, summary, follow-ups, remove button)
- [ ] Create `frontend/components/AddTopicForm.tsx` — inline add form
- [ ] Wire "Extract via Claude" → `POST /api/proxy/calls/{id}/topics/extract`
- [ ] Wire "Validate & Complete" → `POST /api/proxy/calls/{id}/topics` then `POST /api/proxy/calls/{id}/topics/validate`
- [ ] After validation → redirect to `/projects/[id]` (kanban board, call now in Done column)

## Dev Tests
Verify manually:
- Click "Extract via Claude" → loading state → topic list appears
- Edit a topic name → updates locally
- Add a topic → appears in list
- Remove a topic → disappears
- Click "Validate" → call moves to Done, redirected to kanban board
- Click "Add Manually" → empty list, add topics manually, validate → same result
