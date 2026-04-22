# Story 11.6 — End-to-end Validation + Close Epic

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §5 Migration / rollout
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Task 14

---

## Goal
Verify the whole surface works end-to-end, produce a consolidated manual-test document the user can walk through in one sitting, and close the epic.

## Acceptance Criteria
- [ ] Full backend `pytest` suite passes
- [ ] `cd frontend && npx tsc --noEmit && npm run lint` both clean
- [ ] Consolidated manual test file at `docs/project/config/2026-04-22-epic-11-manual-tests.md` with: migration-run checklist, live extraction walkthrough, tile render checks, artifact-type-card checks, project-settings checks, reset-to-default flow, parked topic flow
- [ ] `build-log.md`, `ACTIVE.md`, `codebase.md` updated
- [ ] All 6 stories (11.1–11.6) marked done

## Tasks
Covers Plan Task 14.
