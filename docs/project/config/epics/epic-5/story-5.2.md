# Story 5.2 — Claude Service & SSE Endpoint

**Epic:** EPIC-5 — Artifacts Stage
**Maps to plan:** Slice 5
**Maps to PRD:** US-03, US-04, FR-05, FR-13, NFR-01, NFR-02, NFR-08
**Status:** `pending`

---

## Goal
Railway FastAPI generates all selected "claude" artifacts in parallel and streams per-artifact status to the frontend via SSE. Manual artifacts are skipped. One failure does not block others.

## Acceptance Criteria
- [ ] `POST /api/calls/{call_id}/artifacts` accepts a list of `{artifact_type_id, mode}` selections
  - Creates artifact rows: `mode = 'claude'` → `status = 'pending'`; `mode = 'manual'` → `status = 'done'` with empty content
- [ ] `GET /api/calls/{call_id}/artifacts/stream` opens an SSE stream
  - All `'claude'` artifacts start generating simultaneously (parallel, not sequential)
  - Each artifact emits events: `{"type":"status","artifact_id":"...","status":"generating"}` then `{"type":"done","artifact_id":"...","content":"..."}` or `{"type":"error","artifact_id":"...","message":"..."}`
  - Final event: `{"type":"complete"}`
  - Stream closes after final event
- [ ] Each artifact row's `prompt_used` is set to the artifact type's current prompt at generation time (immutable snapshot)
- [ ] Claude model used: `claude-sonnet-4-6`
- [ ] Rate limit (429): retry with exponential backoff (max 3 retries), then mark artifact as `error`
- [ ] One artifact error does not block the others
- [ ] All Claude calls logged: start, token count on success, error on failure
- [ ] NFR-08: no generation starts until `POST /api/calls/{id}/artifacts` is explicitly called

## Tasks
- [ ] Create `backend/services/claude_service.py` — `generate_artifact(artifact_id, prompt, transcript) → str`
- [ ] Implement retry logic in `claude_service.py` (3 retries, exponential backoff on 429)
- [ ] Create `backend/routers/artifacts.py` — POST to create selections, GET `/stream` SSE endpoint
- [ ] `POST` creates artifact rows with `prompt_used` snapshot
- [ ] `GET /stream` uses `asyncio.as_completed` for parallel generation
- [ ] Register router in `backend/main.py`
- [ ] Write tests: `backend/tests/test_artifacts.py` (mock Anthropic client)

## Dev Tests
- `backend/tests/test_artifacts.py`:
  - `POST` with 3 claude + 2 manual → 5 artifact rows created; manual rows have `status='done'`
  - `GET /stream` (mocked Claude) → all 3 claude artifacts emit `generating` then `done` events
  - `GET /stream` where one Claude call raises → that artifact emits `error`; stream still completes
  - `prompt_used` on artifact row matches the artifact type's prompt at creation time
