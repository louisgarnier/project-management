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

## ✅ UI mockups approved — 2026-04-13
- Per-call Topics stage: brief panel + extraction choice + three-bucket view (followed-up / not-discussed / new) — approved
- Topics dashboard: **Option A (table view)** — approved

---

## Topic fields (confirmed 2026-04-13)
| Field | Type | Notes |
|---|---|---|
| `name` | string | |
| `summary` | string | |
| `follow_up_items` | string[] | Editable per-call |
| `decisions` | string[] | Permanent log of agreements; append-only |
| `status` | `open` / `in_progress` / `resolved` | |
| `owner` | `"Us"` / `"Client"` / `"Both"` | |
| `sentiment` | `positive` / `neutral` / `concern` | |
| `calls_open` | number | Staleness counter — shown as badge "Open · N calls" when N ≥ 2 |
| `archived` | boolean | Soft-deleted; hidden from active views |

---

## Pre-call brief panel

Before the user chooses "Extract via Claude" or "Add Manually", show a **brief panel** (collapsible) that calls `GET /brief`:
- Priority topics (sorted by `calls_open` desc, concern-first)
- Decisions to confirm from last call
- Watch-list topics (sentiment = concern)

Brief is read-only. Collapsed by default on Call 1 (empty).

---

## Three-bucket extraction view (Call 2+)

After "Extract via Claude" completes, the topic list is split into three visually distinct sections:

| Section | Colour cue | User action |
|---|---|---|
| **Followed-up** | Normal / white | Review + edit (pre-filled by Claude) |
| **Not discussed** | Amber warning banner | Must set disposition before validating: update status, archive, or "Keep as-is" |
| **New** | Light blue tint | Review + edit |

"Validate & Complete Call" button is **disabled** until every not-discussed topic has a disposition.

---

## Acceptance Criteria

### Per-call Topics stage
- [ ] Pre-call brief panel shown above extraction choice; collapses if no prior topics (NFR-08: no API call until user opens it)
- [ ] Topics stage shows two clearly labelled options: "Extract via Claude" and "Add Manually" (NFR-08: no API call until user clicks)
- [ ] "Extract via Claude" Call 1: spinner → flat topic list for review
- [ ] "Extract via Claude" Call 2+: spinner → three-bucket view (Followed-up / Not discussed / New)
- [ ] "Add Manually": empty topic list, user adds topics via inline form
- [ ] Each topic shows all 9 fields; all editable inline except `decisions` (append-only) and `calls_open` (computed)
- [ ] Not-discussed topics show amber banner; "Validate & Complete Call" disabled until each has a disposition (status update, archive, or explicit "Keep as-is")
- [ ] Staleness badge: topics with `calls_open ≥ 2` show "Open · N calls" badge in amber
- [ ] User can add, remove, archive, and reorder topics
- [ ] "Validate & Complete Call" → `POST /topics` (save) then `POST /topics/validate` → call moves to Done on kanban
- [ ] Error state: Claude extraction fails → error message + "Try Again"

### Topics dashboard (Topics tab on board)
- [ ] Layout: **table view (Option A, confirmed 2026-04-13)** — name+summary, status badge, staleness badge, owner, sentiment, follow-ups, decisions count, call ref
- [ ] Shows all non-archived topics across all calls for the project
- [ ] Filterable by status (Open / In Progress / Resolved) and by `calls_open` (stale first)
- [ ] Each topic shows: name, status badge, staleness badge (if `calls_open ≥ 2`), owner, sentiment badge, follow-up items, decisions count, call reference
- [ ] Resolved topics visually de-emphasised
- [ ] Archived topics hidden by default; toggle to show

## Tasks
- [ ] **UI mockup review** — invoke `ui-mockup`, get approval on both screens before writing code (present Options A and B for dashboard layout)
- [ ] Create `frontend/src/components/TopicsStage.tsx` — per-call stage component (brief panel + extraction choice + three-bucket view)
- [ ] Create `frontend/src/components/TopicEditor.tsx` — single topic row (all 9 fields, editable; decisions append-only)
- [ ] Create `frontend/src/components/AddTopicForm.tsx` — inline add form
- [ ] Create `frontend/src/components/PreCallBrief.tsx` — collapsible brief panel
- [ ] Create `frontend/app/projects/[id]/topics/page.tsx` (or update board Topics tab) — dashboard view
- [ ] Wire all API calls via `topicsAPI` in `frontend/src/api/client.ts` (extract, save, validate, brief, dashboard GET)
- [ ] After validation → reload kanban board (call now in Done)
