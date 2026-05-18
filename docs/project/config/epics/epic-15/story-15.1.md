# Story 15.1 — Schema + Backend Extractor + Edit Endpoints + Prompt Resolution

**Epic:** EPIC-15 — Call Topics Rebuild
**Status:** [ ] todo
**Spec:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md` §3.1, §4, §5
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md`
**Blocks:** Stories 15.2, 15.3, 15.4

## Goal
Lay the backend foundation: single migration `024` reshapes `topic_updates` (adds `evidence` / `key_terms` / `tasks` JSONB, drops 6 legacy columns) and adds `calls.call_topics_prompt_id` FK. Rewrite `topics_service.py` to validate the new schema, reject invalid topics, resolve prompts from the artifact library (no Python fallback), and support full inline-edit flows. Expand the aggregate endpoint and add a per-call prompt-selection endpoint.

## Acceptance Criteria
- [ ] `backend/database/migrations/024_epic15_call_topics_schema.sql` applied:
  - [ ] ADDS `topic_updates.evidence JSONB NOT NULL DEFAULT '[]'::jsonb`
  - [ ] ADDS `topic_updates.key_terms JSONB NOT NULL DEFAULT '[]'::jsonb`
  - [ ] ADDS `topic_updates.tasks JSONB NOT NULL DEFAULT '[]'::jsonb`
  - [ ] DROPS `decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, `owner` from `topic_updates`
  - [ ] ADDS `calls.call_topics_prompt_id UUID NULL REFERENCES artifact_library(id) ON DELETE SET NULL`
  - [ ] CREATE INDEX `idx_calls_prompt_id`
- [ ] `backend/prompts/call_topics.py` gutted: `CALL_TOPICS_DEFAULT_PROMPT` removed; only `CALL_TOPICS_V2_PROMPT_BODY` remains (exported for seed only).
- [ ] `backend/services/topics_service.py`:
  - [ ] `_TOPIC_SCHEMA` updated to the new locked shape (PRD FR-01).
  - [ ] `TopicIn` / `TopicOut` Pydantic models rewritten; no legacy fields.
  - [ ] `extract_call_topics(call_id)` resolves prompt from library via `calls.call_topics_prompt_id` → fallback to `artifact_library` row where `category=call_topics AND seeded_by_default=true`. **Hard error if neither found.**
  - [ ] Validation rejects topics missing `evidence` or `tasks`; reject count surfaced.
  - [ ] Each persisted task in JSONB carries a fresh UUID `task_id`.
  - [ ] `status` column on `topic_updates` populated as roll-up of task statuses (`open` if any open, `in_progress` if any in_progress, else `resolved`).
- [ ] `backend/routers/topics.py`:
  - [ ] PATCH `/api/topics/{topic_id}` accepts partial body `{name?, importance?, key_terms?, evidence?, tasks?}` and replaces the full tasks array on tasks-patch.
  - [ ] DELETE `/api/topics/{topic_id}` works.
  - [ ] Aggregate endpoint payload now includes `key_terms`, `evidence`, `tasks` per topic.
- [ ] `backend/routers/calls.py`: PATCH `/api/calls/{id}` (or new `/prompt-selection` route) accepts `{call_topics_prompt_id: uuid|null}` and persists.
- [ ] Structured log line in extractor: `📥 [CallTopics] extract call={id} prompt={lib_entry_name} model={provider}/{model_id} topics_produced={n} topics_rejected={n} latency_ms={t}`.
- [ ] Unit tests in `backend/tests/test_topics_service.py`:
  - [ ] Validates rejection of malformed topics (no evidence, no tasks, missing required fields).
  - [ ] Verifies prompt resolution path (call.prompt_id → library → hard error).
  - [ ] Round-trip PATCH/GET asserts JSON shape equality.

## Out of scope (in this story)
- Library seed changes (Story 15.2).
- Any frontend code (Story 15.3 / 15.4).
- Real-fixture acceptance + rollback regression test (Story 15.4).
