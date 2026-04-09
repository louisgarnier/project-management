# Story 2.1 — Projects API

**Epic:** EPIC-2 — Projects
**Maps to plan:** Slice 2
**Maps to PRD:** US-01, FR-01
**Status:** `pending`

---

## Goal
Railway FastAPI exposes CRUD for projects. Postman/curl can create, list, and delete projects.

## Acceptance Criteria
- [ ] `GET /api/projects` returns list of all projects (id, name, description, created_at)
- [ ] `POST /api/projects` creates a project, returns the created row
- [ ] `DELETE /api/projects/{id}` deletes project and cascades to calls/artifacts/topics
- [ ] All endpoints log requests via logging middleware (from Story 1.2)
- [ ] Supabase operations logged via `db_logger`
- [ ] 404 returned (not 500) when deleting a non-existent project
- [ ] Tests pass: happy path + missing project

## Tasks
- [ ] Create `backend/routers/projects.py` with GET, POST, DELETE
- [ ] Register router in `backend/main.py` with prefix `/api`
- [ ] Add db_logger calls for each Supabase operation
- [ ] Write tests: `backend/tests/test_projects.py`

## Dev Tests
- `backend/tests/test_projects.py`:
  - `GET /api/projects` → 200, returns list (can be empty)
  - `POST /api/projects` with `{name, description}` → 201, returns project with id
  - `DELETE /api/projects/{id}` with valid id → 204
  - `DELETE /api/projects/nonexistent-id` → 404
