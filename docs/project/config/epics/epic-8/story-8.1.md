# Story 8.1 — Full Test Suite

**Epic:** EPIC-8 — Testing & Deployment
**Maps to PRD:** NFR-01, NFR-02, NFR-05
**Status:** `pending`

---

## Goal
All backend tests pass with zero failures. Every functional requirement has at least one test.

## Acceptance Criteria
- [ ] `pytest backend/tests/ -v` runs clean — zero failures
- [ ] Coverage report generated (`pytest --cov=backend`)
- [ ] Every FR from the PRD mapped to at least one test:
  - FR-02 (transcript storage), FR-05 (parallel generation), FR-07 (block advancement), FR-09 (topic chain), FR-09b (sequential enforcement), FR-10 (validate before done), FR-13 (prompt snapshot immutability)
- [ ] Integration smoke test: full pipeline from project creation → call → transcript → artifacts → topics → done runs without error

## Tasks
- [ ] Review test coverage report — identify untested paths
- [ ] Add missing tests for each uncovered FR
- [ ] Write integration test: `backend/tests/test_integration.py` — full pipeline with mocked Claude
- [ ] Fix any flaky tests
- [ ] Verify `prompt_used` immutability: update artifact type prompt, confirm existing artifact row unchanged

## Dev Tests
- `backend/tests/test_integration.py`:
  - Create project → create call → POST transcript → POST artifact selections → GET stream (mocked) → POST topics → POST validate → call is `'done'`
  - Second call creation before first is done → 409
  - All 5 artifacts generate independently (one error doesn't block others)
