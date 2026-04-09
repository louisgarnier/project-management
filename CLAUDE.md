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

## Story execution process — follow this EXACTLY, every story, no exceptions

The full project brainstorm, PRD, architecture, logging, and epic breakdown are ALREADY DONE.
`docs/project/requirements/` is the source of truth. `docs/project/config/epics/` has all stories defined.

**For every new story, the process is:**

1. Read `docs/project/config/epics/ACTIVE.md` → identify current story
2. Read the story file (`docs/project/config/epics/epic-X/story-X.Y.md`) → AC and tasks are already defined
3. **Backend story** → go straight to writing the implementation plan, then execute
4. **UI story** → show a visual mockup for approval (visual companion only), then write plan, then execute
5. Write implementation plan → save to `docs/project/config/YYYY-MM-DD-story-X.Y-<name>-plan.md`
6. Execute plan via `superpowers:subagent-driven-development`
7. After all tasks pass: update `build-log.md`, `codebase.md`, close story, advance `ACTIVE.md`

### HARD RULES — violations are bugs in your behaviour

- **NEVER invoke `superpowers:brainstorming` for a story or epic.** Brainstorming was done once at project start. It is complete. Invoking it again wastes time and creates duplicate work.
- **NEVER say "this epic needs brainstorming".** The epics and stories are pre-defined. Read them.
- **NEVER invent stories** (e.g. "Story 3.3") that don't exist in `docs/project/config/epics/`. If a story file doesn't exist, ask the user before doing anything.
- **NEVER advance to an epic** that doesn't have story files in `docs/project/config/epics/`. Stop and tell the user the story files need to be created first.
- **The only time `superpowers:brainstorming` is allowed** is if the user explicitly rejects an existing design and asks to redesign it from scratch.

### Superpowers skills — when to use each
| Skill | When to use | When NOT to use |
|---|---|---|
| `superpowers:subagent-driven-development` | Every story — executes the plan | — |
| `superpowers:writing-plans` | Every story — writes the implementation plan | — |
| `superpowers:systematic-debugging` | When a bug is encountered | — |
| `superpowers:test-driven-development` | When writing code | — |
| `superpowers:verification-before-completion` | Before closing a story | — |
| `superpowers:brainstorming` | **Step 1 only** (1-BRAINSTORM.md), or if a design is explicitly rejected and needs rethinking | Never for a story/epic that already has AC defined in `docs/project/config/epics/` |

**Key principle:** Superpowers skills are tools. Use them when they help. Don't re-run a skill for work that's already done. The brainstorm, PRD, architecture, and epics for this project are complete — don't redo them.

## Sealed files — never read or modify during development
- `docs/project/testing/BLIND_SCENARIOS.md`
