# Story 7.2 — Topic Dashboard UI

**Epic:** EPIC-7 — Topic Dashboard
**Maps to plan:** Slice 7
**Maps to PRD:** US-10, FR-11, FR-11b
**Status:** `pending`

---

## Goal
The "Topics" tab on the project page shows all topics in a structured dashboard. User can change topic status, edit content, add new topics, and remove topics — at any time.

## Acceptance Criteria
- [ ] "Topics" tab on project page loads `TopicDashboard` component
- [ ] Each topic shows: name, status (dropdown), latest update summary, open follow-up items, call history (collapsible)
- [ ] Status dropdown has 4 options: `Active` · `Decision Made` · `On Hold` · `Closed`
- [ ] Changing status calls `PATCH /api/proxy/topics/{id}` immediately
- [ ] "Add Topic" form: name input → creates topic via `POST /api/proxy/projects/{id}/topics`
- [ ] "Remove" button per topic → calls `DELETE /api/proxy/topics/{id}`, confirms before deleting
- [ ] Call history section: each past update shown as `[Call Title] — summary`, collapsible
- [ ] Empty state: "No topics yet — process your first call to extract topics, or add one manually"

## Tasks
- [ ] Create `frontend/components/TopicDashboard.tsx` — fetches + renders all topics
- [ ] Create `frontend/components/TopicCard.tsx` — name, status dropdown, latest update, follow-ups, history toggle
- [ ] Create `frontend/components/AddTopicForm.tsx` (reuse or extend from EPIC-6 if applicable)
- [ ] Wire status change → `PATCH` on dropdown change
- [ ] Wire delete → confirmation dialog then `DELETE`
- [ ] Update `frontend/app/projects/[id]/page.tsx` — wire Topics tab to `TopicDashboard`

## Dev Tests
Verify manually:
- Process one full call through the pipeline → Topics tab shows extracted topics
- Change status from Active → Closed → persisted after page refresh
- Add a topic manually → appears in dashboard
- Remove a topic → disappears after confirmation
- Expand call history → shows update from the processed call
