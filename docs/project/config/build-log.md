# Build Log — Call Tracker

## Current Stage
**EPIC-3 / Story 3.3 — (next story)**
- Status: not started
- Blocked by: nothing

---

## Session History

### 2026-04-09 — Story 3.2: Kanban Board UI
- Live BoardPage fetching calls from GET /api/projects/{id}/calls
- KanbanBoard: 4 columns (Get Transcript / Artifacts / Topics / Done) with CallCard per call
- CallCard: colored left border, stage badge, date, hover shadow, done opacity 0.65
- NewCallModal: title input, POST on submit, reloads board on success
- "+ New Call" disabled with tooltip when active call exists (hasActiveCall guard)
- Placeholder call detail page at /projects/[id]/calls/[call_id]
- Tabs: Kanban (live) + Topics (placeholder)
- TypeScript clean, ESLint clean, Prettier clean

### 2026-04-09 — Story 3.1: Calls API
- Implemented GET /api/projects/{id}/calls, POST /api/projects/{id}/calls, GET /api/calls/{id}, PATCH /api/calls/{id}/stage
- 409 sequential enforcement: only one active call per project
- Stage transitions: transcript → artifacts → topics → done (422 on skip)
- 9 new tests, 22 total passing
- ruff + black clean

### 2026-04-09 — EPIC-1 wrap-up + next@15 upgrade
**Completed:** EPIC-1 (Stories 1.1, 1.2, 1.3) verified and closed
**Fixes applied:**
- ruff auto-fixed 10 import-sort errors in backend/
- Recreated `backend/.env.example` (had been deleted)
- Upgraded `next@16.0.3` (CVE) → `next@15.x` (stable, 0 vulnerabilities)
- Upgraded `eslint@8` → `eslint@9` (flat config via `@eslint/eslintrc` FlatCompat)
- Created `frontend/eslint.config.mjs` replacing `.eslintrc.json`
- Fixed `frontend/src/utils/logger.ts` — ternary-as-statement → if/else
- Logged upgrade as ADR-001

**Verification (all passing):**
- 8/8 backend tests pass
- ruff: 0 errors, black: 0 changes
- ESLint (frontend): 0 errors, 0 warnings

**Next session starts at:** EPIC-2 / Story 2.1 — Projects API

### 2026-04-09 — EPIC-2 / Story 2.1 — Projects API
**Completed:** Projects CRUD API
**Built:**
- `backend/routers/projects.py` — GET /api/projects, POST /api/projects, DELETE /api/projects/{id}
- `backend/main.py` — router registered with `/api` prefix
- `backend/tests/test_projects.py` — 5 tests (TDD, all passing)

**Verification:**
- 13/13 backend tests pass
- 404 on delete non-existent project (not 500)
- db_logger on every Supabase operation

**Next session starts at:** EPIC-2 / Story 2.2 — Project List UI

### 2026-04-09 — EPIC-2 / Story 2.2 — Project List UI
**Completed:** Project list, create modal, project detail placeholder
**Built:**
- `frontend/app/page.tsx` — fetches projects, shows list + create button
- `frontend/src/components/ProjectList.tsx` — list with empty state
- `frontend/src/components/CreateProjectModal.tsx` — form (name + description)
- `frontend/app/projects/[id]/page.tsx` — placeholder page
- `frontend/src/api/client.ts` — added `projectsAPI` (list, create, delete)

**Verification:**
- ESLint: 0 errors
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement

### 2026-04-09 — EPIC-2 / Story 2.3 — App Shell & Project List UI (Redesign)
**Completed:** Jira-like app shell — top nav, sidebar, per-project nav, placeholder pages
**Built:**
- `frontend/src/components/TopNav.tsx` — blue top nav (static server component)
- `frontend/src/components/Sidebar.tsx` — client component, project list + per-project nav, create modal, hash-stable colours, error logging
- `frontend/src/components/CallCard.tsx` — placeholder card component for EPIC-3
- `frontend/app/layout.tsx` — root layout with shell (TopNav + Sidebar + main)
- `frontend/app/page.tsx` — "select a project" landing
- `frontend/app/projects/[id]/page.tsx` — redirects to /board
- `frontend/app/projects/[id]/board/page.tsx` — 4-column kanban placeholder
- `frontend/app/projects/[id]/topics/page.tsx` — placeholder
- `frontend/app/projects/[id]/history/page.tsx` — placeholder
- Deleted `frontend/src/components/ProjectList.tsx`

**Verification:**
- ESLint: 0 errors, 0 warnings
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement
