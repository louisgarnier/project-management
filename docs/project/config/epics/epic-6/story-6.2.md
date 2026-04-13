# Story 6.2 — Topics Stage UI

**Epic:** EPIC-6 — Topics Stage
**Maps to plan:** Slice 6
**Maps to PRD:** US-06, FR-08, FR-09, NFR-08
**Status:** `pending`

---

## Goal
The Topics stage has two parts:
1. **Per-call Topics stage** — inside the call flow: extract or manually enter topics for this call, review/edit, then validate to move the call to Done.
2. **Project Topics dashboard** — the Topics tab on the board: shows all topics across all calls, grouped/filtered by status.

---

## ⚠️ STOP — UI mockup required before any code

**Before writing a single line of UI code for either screen, invoke `ui-mockup` and get user approval on:**

### Per-call Topics stage mockup
Show the full flow:
- Initial choice screen: "Extract via Claude" vs "Add Manually"
- Topic list view: each topic shows name, summary, follow-up items, status, owner, sentiment — all editable
- "Validate & Complete Call" button

### Topics dashboard mockup
Two layout options were discussed on 2026-04-13 (see `.superpowers/brainstorm/20762-1776069130/content/topics-dashboard.html`):
- **Option A** — table view (name, status, owner, sentiment, follow-ups, call ref)
- **Option B** — cards grouped by status (Open / In Progress / Resolved), colour-coded left border

**User has not yet chosen between A and B. Present both options again and get a decision before building.**

---

## Topic fields (confirmed 2026-04-13)
| Field | Type |
|---|---|
| `name` | string |
| `summary` | string |
| `follow_up_items` | string[] |
| `status` | `open` / `in_progress` / `resolved` |
| `owner` | `"Us"` / `"Client"` / `"Both"` |
| `sentiment` | `positive` / `neutral` / `concern` |

## Acceptance Criteria

### Per-call Topics stage
- [ ] Topics stage shows two clearly labelled options: "Extract via Claude" and "Add Manually" (NFR-08: no API call until user clicks)
- [ ] "Extract via Claude": spinner while extraction runs, then topic list appears for review
- [ ] "Add Manually": empty topic list, user adds topics via inline form
- [ ] Each topic shows all 6 fields, all editable inline
- [ ] User can add, remove, and reorder topics
- [ ] "Validate & Complete Call" → `POST /topics` (save) then `POST /topics/validate` → call moves to Done on kanban
- [ ] Error state: Claude extraction fails → error message + "Try Again"

### Topics dashboard (Topics tab on board)
- [ ] Layout: **decided at mockup review** (table or grouped cards — not yet chosen)
- [ ] Shows all topics across all calls for the project
- [ ] Filterable by status (Open / In Progress / Resolved)
- [ ] Each topic shows: name, status badge, owner, sentiment badge, follow-up items, call reference
- [ ] Resolved topics visually de-emphasised

## Tasks
- [ ] **UI mockup review** — invoke `ui-mockup`, get approval on both screens before writing code
- [ ] Create `frontend/src/components/TopicsStage.tsx` — per-call stage component
- [ ] Create `frontend/src/components/TopicEditor.tsx` — single topic row (all 6 fields, editable)
- [ ] Create `frontend/src/components/AddTopicForm.tsx` — inline add form
- [ ] Create `frontend/app/projects/[id]/topics/page.tsx` (or update board Topics tab) — dashboard view
- [ ] Wire all API calls via `topicsAPI` in `frontend/src/api/client.ts`
- [ ] After validation → reload kanban board (call now in Done)
