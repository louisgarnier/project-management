# Story 2.3 — App Shell & Project List UI (Redesign)

**Epic:** EPIC-2 — Projects
**Maps to plan:** docs/superpowers/plans/2026-04-09-story-2.3-ui-shell.md
**Maps to spec:** docs/superpowers/specs/2026-04-09-ui-shell-design.md
**Status:** `pending`

---

## Goal
Replace the placeholder project list with a Jira-like app shell: dark blue top nav,
light grey sidebar with project list + per-project navigation (Board, Topics, File History),
and routed placeholder pages for each section.

## Acceptance Criteria
- [ ] Top nav: blue (#0052cc) bar with CT logo and wordmark
- [ ] Sidebar: project list with colour avatars, active project highlighted
- [ ] Sidebar: "+ New project" triggers CreateProjectModal
- [ ] Creating a project navigates to that project's board
- [ ] Per-project nav appears when a project URL is active (Board · Topics · File History)
- [ ] Active sidebar item is highlighted correctly for current URL
- [ ] `/` shows "select a project" landing screen
- [ ] `/projects/[id]` redirects to `/projects/[id]/board`
- [ ] Board page: 4 kanban column placeholders (Transcript, Artifacts, Topics, Done)
- [ ] Topics page: placeholder panel
- [ ] File History page: placeholder panel
- [ ] ESLint: 0 errors, 0 warnings

## Tasks
- [ ] Create TopNav component
- [ ] Create Sidebar component
- [ ] Update root layout with shell
- [ ] Update home page (landing)
- [ ] Update /projects/[id] page (redirect)
- [ ] Create board placeholder page
- [ ] Create topics placeholder page
- [ ] Create file history placeholder page
- [ ] Remove ProjectList.tsx
- [ ] ESLint pass + manual test
