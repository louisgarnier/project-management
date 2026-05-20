# Story 11.1 — Schema & Prompt Foundation

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `done` — 2026-04-22
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §4.1–4.3, §4.6
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Tasks 1–3

---

## Goal
Lay the foundation: DB columns for the enriched topic schema + OpenRouter model field, a single-source-of-truth Python module holding the new rubric-driven prompt, and updated Pydantic + `_TOPIC_SCHEMA` so extractions round-trip the four new fields.

## Acceptance Criteria
- [x] Migration 019 adds `open_questions JSONB`, `is_parked BOOL`, `importance TEXT`, `rationale TEXT` to `topic_updates`; adds `model TEXT` to `artifact_types`; adds `default_model TEXT` to `projects`
- [x] `backend/prompts/call_topics.py` exports `CALL_TOPICS_DEFAULT_PROMPT` with all 5 named blocks (ROLE/RUBRIC/ANCHORS/FEW-SHOT/PROCESS) and `OLD_DEFAULT_PROMPT_STRING` frozen snapshot
- [x] `TopicIn` / `TopicOut` carry `open_questions: list[str]`, `is_parked: bool`, `importance: Literal["high","medium","low"]`, `rationale: str` with sensible defaults
- [x] `_TOPIC_SCHEMA` and `_normalize_topic` reflect the new fields
- [x] `extract_call_topics` imports and uses the new constant as fallback (no inline duplicate)
- [x] All existing topic tests still pass; new tests cover the 4 new fields + prompt-block presence

## Tasks
Covers Plan Task 1 (migration 019), Task 2 (prompt constants module + tests), Task 3 (Pydantic models + schema + fallback wiring).
