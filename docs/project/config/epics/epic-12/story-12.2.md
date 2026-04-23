# Story 12.2 — Artifact Library (Seed + CRUD API)

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** pending
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §4.3, §4.13
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Tasks 3–4

## Goal
Seed 8 canonical entries into the new `artifact_library` table on backend startup (idempotent), and expose CRUD API for managing the shared pool. System entries can be edited but not hard-deleted; a reset-system endpoint restores original values.

## Acceptance Criteria
- [ ] `backend/library/seed.py` exports `SYSTEM_LIBRARY: list[dict]` with 8 entries (3 seeded-by-default, 5 opt-in)
- [ ] `upsert_system_library(db)` inserts missing entries, preserves existing ones; returns `{inserted: N, preserved: M}`
- [ ] Startup hook in `main.py::lifespan` calls upsert on boot, logs result
- [ ] `backend/routers/library.py` exposes `GET /api/library`, `POST /api/library`, `PATCH /api/library/{id}`, `DELETE /api/library/{id}`, `POST /api/library/reset-system`
- [ ] DELETE returns 403 when `is_system=true`
- [ ] POST reset-system re-applies SYSTEM_LIBRARY values to `is_system=true` rows (8 updates)
- [ ] Library CRUD tests: 6 unit tests cover list/create/patch/delete-user/delete-system/reset-system
- [ ] Seed tests: 5 unit tests verify SYSTEM_LIBRARY shape + idempotent upsert

## Tasks
Covers Plan Task 3 (seed module + startup hook), Task 4 (CRUD API router).
