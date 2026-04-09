# Story 2.2 — Project List UI

**Epic:** EPIC-2 — Projects
**Maps to plan:** Slice 2
**Maps to PRD:** US-01
**Status:** `done` — superseded by Story 2.3 which delivered all AC. Validated 2026-04-09.

---

## Goal
The app opens to a project list. User can create a project and click into it. Testable in browser.

## Acceptance Criteria
- [x] `/` (home) shows list of all projects, each with name + description
- [x] "New Project" button opens a create form (name + description)
- [x] Submitting the form calls `POST /api/projects` via proxy and adds the project to the list
- [x] Clicking a project navigates to `/projects/[id]` (placeholder page for now — just shows project name)
- [x] All API calls log via `frontend/src/utils/logger.ts` (browser console + proxy terminal)
- [x] Empty state: "No projects yet — create your first one" shown when list is empty

## Tasks
- [x] Create `frontend/app/page.tsx` — project list with fetch from `/api/proxy/projects`
- [x] Create `frontend/components/ProjectList.tsx` — renders list + empty state
- [x] Create `frontend/components/CreateProjectModal.tsx` — form with name + description
- [x] Create `frontend/app/projects/[id]/page.tsx` — placeholder showing project name
- [x] Wire logger calls: log API fetch start/success/error in components

## Dev Tests
No automated frontend tests at this stage — verify manually:
- Start both Railway FastAPI and Next.js dev server
- Open `localhost:3000` → project list renders
- Create a project → appears in list
- Click project → navigates to `/projects/[id]`
