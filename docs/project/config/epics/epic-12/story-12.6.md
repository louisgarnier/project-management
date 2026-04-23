# Story 12.6 — End-to-End Validation + Close Epic

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** pending
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §5 Migration / rollout
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Task 14

## Goal
Verify the whole surface works end-to-end. Produce a consolidated manual-test document the user walks through in one sitting. Close the epic (update build-log, ACTIVE, codebase, mark stories done).

## Acceptance Criteria
- [ ] Full backend `pytest` suite passes (pre-existing failures documented, no EPIC-12 regressions)
- [ ] `cd frontend && npx tsc --noEmit && npm run lint` both clean
- [ ] Consolidated manual test file at `docs/project/config/2026-04-23-epic-12-manual-tests.md` covering: migration 021 run, backend startup seeds library, existing project unchanged, new project seeding, library flow (add from library + publish + edit), generation flow (LLM + template + hybrid), cost verification
- [ ] `build-log.md`, `ACTIVE.md`, `codebase.md` updated
- [ ] All 6 stories (12.1–12.6) marked done

## Tasks
Covers Plan Task 14.
