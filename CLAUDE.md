## Project: [NAME]
One-liner: [fill in from brainstorm]
Current stage: Step 1 — Brainstorm

## Non-goals — these are LAW, do not implement
- [fill from locked PRD — leave blank until PRD is done]

## Stack
- Frontend: [fill from architecture]
- Backend: [fill from architecture]
- Database: [fill from architecture]

## Session start — read these files in order before any code
1. `docs/project/config/build-log.md` — current stage + blockers
2. `docs/project/config/codebase.md` — existing modules
3. `workflow/ERRORS.md` — known problem areas
4. `workflow/ADR.md` — architectural decisions already made
5. `docs/project/config/epics/ACTIVE.md` — current story (once epics are defined)

## File locations — NEVER put files anywhere else

| File type | Location | Example |
|---|---|---|
| Specs / design docs | `docs/project/config/` | `docs/project/config/2026-04-09-story-3.2-kanban-board-design.md` |
| Implementation plans | `docs/project/config/` | `docs/project/config/2026-04-09-story-3.2-kanban-board-plan.md` |
| Epic / story files | `docs/project/config/epics/` | `docs/project/config/epics/epic-3/story-3.2.md` |
| Build log | `docs/project/config/build-log.md` | — |
| Codebase map | `docs/project/config/codebase.md` | — |

**NEVER save specs or plans to `docs/superpowers/` — that folder does not exist for this project.**

## Story execution process
Follow global CLAUDE.md Step 6 exactly. Steps 1–5 are already complete for this project.

This project is currently at **Step 6 — Build**. All epics and stories are defined in `docs/project/config/epics/`.

## Sealed files — never read or modify during development
- `docs/project/testing/BLIND_SCENARIOS.md`
