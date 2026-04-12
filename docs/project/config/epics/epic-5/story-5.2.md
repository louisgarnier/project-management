# Story 5.2 — Artifact Types API

**Epic:** EPIC-5 — Artifacts Stage
**Maps to plan:** Slice 5
**Maps to PRD:** US-11, US-12, FR-04, FR-12, FR-13
**Status:** `pending`
**Depends on:** Story 5.1 (defines the data model requirements)

---

## Goal
Railway FastAPI exposes CRUD for artifact types, scoped per project. The 6 defaults are seeded at project creation. Users can add custom types, edit prompts, and import types from other projects. Each type returns its current prompt for snapshotting at generation time.

## Data model
Artifact types are **project-scoped** — `artifact_types` table has a `project_id` FK. The 6 defaults are inserted when a project is created (not as a global seed). Importing from another project creates independent copies with the new `project_id`.

## Acceptance Criteria
- [ ] `GET /api/projects/{project_id}/artifact-types` returns all types for the project (id, name, prompt, is_default)
- [ ] `POST /api/projects/{project_id}/artifact-types` creates a new custom type with name + prompt
- [ ] `PATCH /api/projects/{project_id}/artifact-types/{id}` updates name and/or prompt
- [ ] `DELETE /api/projects/{project_id}/artifact-types/{id}` deletes custom types only — 403 if `is_default = TRUE`
- [ ] `POST /api/projects/{project_id}/artifact-types/import` — accepts `{type_ids: [uuid]}` from any project, creates independent copies in target project
- [ ] 6 defaults seeded automatically when a new project is created (hook into `POST /api/projects`)
- [ ] All operations logged

## Tasks
- [ ] Create `backend/routers/artifact_types.py` with GET, POST, PATCH, DELETE, import
- [ ] Add guard in DELETE: 403 if `is_default = TRUE`
- [ ] Add import endpoint: fetch source types by ID, insert copies with new `project_id` and `is_default = FALSE`
- [ ] Hook 6-default seed into `POST /api/projects` in `projects.py`
- [ ] Register router in `backend/main.py`
- [ ] Write tests: `backend/tests/test_artifact_types.py`

## Dev Tests
- `GET` → returns list scoped to project (not other projects' types)
- `POST` → 201, new type returned
- `PATCH` → prompt updated; existing artifact rows unaffected (`prompt_used` is immutable)
- `DELETE` custom type → 204
- `DELETE` default type → 403
- `import` → copies appear in target project; originals unchanged
- New project creation → 6 default types auto-seeded
