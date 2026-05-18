# Story 15.2 — Library Seed: Model Flip + v2 Call-Topics Entry

**Epic:** EPIC-15 — Call Topics Rebuild
**Status:** [ ] todo
**Spec:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md` §3.1 (`backend/library/seed.py`)
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md` G8, FR-13, FR-14, US-12
**Depends on:** Story 15.1 (migration 024 must be live; library schema unchanged but extractor reads from new shape)

## Goal
Update the artifact library seed so new projects start on `openrouter / deepseek-v3.2` and have the rewritten v2 call-topics prompt as their default. Existing projects + existing rows are NOT touched (PRD NG10, Q3=a).

## Acceptance Criteria
- [ ] `backend/library/seed.py` `SYSTEM_LIBRARY` updated:
  - [ ] Every entry where `kind ∈ {llm, hybrid}` has `model="openrouter"` and `model_id="deepseek/deepseek-v3.2"`.
  - [ ] This includes the 4 workflow prompts (`call_topics`, `merge_verification`, `not_discussed_check`, `project_topics`) and every LLM/hybrid artifact-type entry.
- [ ] A new SYSTEM_LIBRARY entry is added:
  - [ ] `name = "Call Topics — v2 (synthetic, evidence-anchored)"`
  - [ ] `category = "call_topics"`
  - [ ] `kind = "llm"`
  - [ ] `seeded_by_default = true`
  - [ ] `prompt` body = `CALL_TOPICS_V2_PROMPT_BODY` imported from `backend/prompts/call_topics.py`
  - [ ] `model = "openrouter"`, `model_id = "deepseek/deepseek-v3.2"`
- [ ] The pre-existing v1 call_topics entry stays in the seed, but with `seeded_by_default = false`. (User can re-enable manually via /library.)
- [ ] `upsert_system_library` (existing idempotent function) cleanly applies the new seed on existing DBs without duplicating rows.
- [ ] `/library` "Reset system to defaults" button preserves v1 demotion (v1 remains `seeded_by_default=false` after reset, not flipped back to true).
- [ ] Unit tests:
  - [ ] `backend/tests/test_library_seed.py` (new or extended): assert every LLM/hybrid system entry resolves to `openrouter / deepseek/deepseek-v3.2`.
  - [ ] Assert v2 call_topics entry exists and is `seeded_by_default=true`.
  - [ ] Assert v1 call_topics entry exists and is `seeded_by_default=false`.
  - [ ] Assert no existing project's `default_model` is modified by the seed call.

## Out of scope (in this story)
- Frontend prompt-selector dropdown (Story 15.3 consumes the library API).
- Real-fixture acceptance (Story 15.4).
- Writing the v2 prompt rubric body itself — that's part of Story 15.1's `CALL_TOPICS_V2_PROMPT_BODY` constant. Story 15.2 only wires it into the library.
