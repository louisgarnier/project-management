# Story 5.1 — Artifact Types API

**Epic:** EPIC-5 — Artifacts Stage
**Maps to plan:** Slice 5
**Maps to PRD:** US-11, US-12, FR-04, FR-12, FR-13
**Status:** `pending`

---

## Goal
Railway FastAPI exposes CRUD for artifact types. The 6 defaults are seeded (from Story 1.3). User can add custom types and edit prompts. Each type returns its current prompt for snapshotting at generation time.

## Acceptance Criteria
- [ ] `GET /api/artifact-types` returns all artifact types (id, name, prompt, is_default)
- [ ] `POST /api/artifact-types` creates a new custom type with name + prompt
- [ ] `PATCH /api/artifact-types/{id}` updates name and/or prompt
- [ ] `DELETE /api/artifact-types/{id}` deletes custom types only — default types cannot be deleted (403)
- [ ] All 6 defaults present after seeding (from Story 1.3) — `is_default = TRUE`
- [ ] All operations logged

## Tasks
- [ ] Create `backend/routers/artifact_types.py` with GET, POST, PATCH, DELETE
- [ ] Add guard in DELETE: reject with 403 if `is_default = TRUE`
- [ ] Register router in `backend/main.py`
- [ ] Write tests: `backend/tests/test_artifact_types.py`

## Dev Tests
- `backend/tests/test_artifact_types.py`:
  - `GET` → returns list with 6 items (after seed)
  - `POST` with name + prompt → 201, new type returned
  - `PATCH` → prompt updated, old artifacts unaffected (prompt_used is immutable on artifact row)
  - `DELETE` custom type → 204
  - `DELETE` default type → 403
