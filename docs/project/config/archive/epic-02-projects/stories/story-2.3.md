# Story 2.3 — App Shell & Project List UI (Redesign)

**Epic:** EPIC-2 — Projects
**Maps to plan:** docs/superpowers/plans/2026-04-09-story-2.3-ui-shell.md
**Maps to spec:** docs/superpowers/specs/2026-04-09-ui-shell-design.md
**Status:** `done`

---

## Goal
Replace the placeholder project list with a Jira-like app shell: dark blue top nav,
light grey sidebar with project list + per-project navigation (Board, Topics, File History),
and routed placeholder pages for each section.

## Acceptance Criteria
- [x] Top nav: blue (#0052cc) bar with CT logo and wordmark
- [x] Sidebar: project list with colour avatars, active project highlighted
- [x] Sidebar: "+ New project" triggers CreateProjectModal
- [x] Creating a project navigates to that project's board
- [x] Per-project nav appears when a project URL is active (Board · Topics · File History)
- [x] Active sidebar item is highlighted correctly for current URL
- [x] `/` shows "select a project" landing screen
- [x] `/projects/[id]` redirects to `/projects/[id]/board`
- [x] Board page: 4 kanban column placeholders (Transcript, Artifacts, Topics, Done)
- [x] Topics page: placeholder panel
- [x] File History page: placeholder panel
- [x] ESLint: 0 errors, 0 warnings

## Tasks
- [x] Create TopNav component
- [x] Create Sidebar component
- [x] Update root layout with shell
- [x] Update home page (landing)
- [x] Update /projects/[id] page (redirect)
- [x] Create board placeholder page
- [x] Create topics placeholder page
- [x] Create file history placeholder page
- [x] Remove ProjectList.tsx
- [x] ESLint pass + manual test
