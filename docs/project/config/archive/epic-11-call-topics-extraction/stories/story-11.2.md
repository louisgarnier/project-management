# Story 11.2 — Prompt Lifecycle

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `done` — 2026-04-22
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §4.6
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Tasks 4–6

---

## Goal
Put the single-source-of-truth pattern into production: migrate existing unedited `call_topics` rows to the new default, expose a reset endpoint, and extract the other three workflow prompts (`project_topics`, `merge_verification`, `not_discussed_check`) + the `artifacts` bundle into parallel constant modules.

## Acceptance Criteria
- [x] `backend/scripts/migrate_call_topics_prompt.py` — exact-string-match migration; returns `{migrated: N, preserved: M}`; customized rows untouched
- [x] `GET /api/artifact-types/defaults/{category}` returns `{name, prompt, llm, model, category}` for known categories; 404 otherwise
- [x] `backend/prompts/{project_topics,merge_verification,not_discussed_check,artifacts}.py` each export a single canonical constant; the corresponding `DEFAULT_*_PROMPT` dicts in `routers/artifact_types.py` reference them
- [x] Seeded defaults for new projects: `call_topics`, `merge_verification`, `not_discussed_check`, and all artifact types now come with `llm='openrouter'` + recommended `model` slug per spec §4.4.4
- [x] Tests: migration preserves customized rows; reset endpoint returns canonical constants; SSOT reference check passes

## Tasks
Covers Plan Task 4 (migration script), Task 5 (reset endpoint), Task 6 (parallel prompt modules).
