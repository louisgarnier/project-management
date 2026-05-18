# Story 15.2 — Library Seed: Model Flip + v2 Call-Topics Entry

**Epic:** EPIC-15 — Call Topics Rebuild
**Status:** [x] done — 2026-05-18
**Spec:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md` §3.1 (`backend/library/seed.py`)
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md` G8, FR-13, FR-14, US-12
**Depends on:** Story 15.1 (migration 024 must be live; library schema unchanged but extractor reads from new shape)

## Goal
Update the artifact library seed so new projects start on `openrouter / deepseek-v3.2` and have the rewritten v2 call-topics prompt as their default. Existing projects + existing rows are NOT touched (PRD NG10, Q3=a).

## Acceptance Criteria
- [x] `backend/library/seed.py` `SYSTEM_LIBRARY` updated:
  - [x] Every entry where `kind ∈ {llm, hybrid}` has `model="openrouter"` and `model_id="deepseek/deepseek-v3.2"`.
  - [x] This includes the 4 workflow prompts (`call_topics`, `merge_verification`, `not_discussed_check`, `project_topics`) and every LLM/hybrid artifact-type entry.
- [x] A new SYSTEM_LIBRARY entry is added:
  - [x] `name = "Call Topics — v2 (synthetic, evidence-anchored)"`
  - [x] `category = "call_topics"`
  - [x] `kind = "llm"`
  - [x] `seeded_by_default = true`
  - [x] `prompt` body = `CALL_TOPICS_V2_PROMPT_BODY` imported from `backend/prompts/call_topics.py`
  - [x] `model = "openrouter"`, `model_id = "deepseek/deepseek-v3.2"`
- [ ] ~~The pre-existing v1 call_topics entry stays in the seed, but with `seeded_by_default = false`.~~ **PRD drift, documented:** the EPIC-11 v1 prompt body was deliberately deleted in Story 15.1 T3 (only `OLD_DEFAULT_PROMPT_STRING`, a pre-EPIC-11 string, remains). The seed therefore ships v2-only. Existing projects whose `artifact_types` row was seeded earlier retain their EPIC-11 prompt content. If the user wants v1 in the library, paste the EPIC-11 prompt into a new entry via `/library` — no code change needed.
- [x] `upsert_system_library` (existing idempotent function) cleanly applies the new seed on existing DBs without duplicating rows.
- [x] `/library` "Reset system to defaults" button preserves v1 demotion (vacuously true — v1 is not in the seed; the v2 default is unambiguous after reset).
- [x] Unit tests:
  - [x] `backend/tests/test_library_seed.py`: assert every LLM/hybrid system entry resolves to `openrouter / deepseek/deepseek-v3.2`.
  - [x] Assert v2 call_topics entry exists and is `seeded_by_default=true`.
  - [ ] ~~Assert v1 call_topics entry exists and is `seeded_by_default=false`.~~ N/A — see PRD drift above. Replaced with: assert there is **exactly one** seeded-by-default call_topics entry (`test_only_one_call_topics_default`).
  - [x] Assert no existing project's `default_model` is modified by the seed call.

## Out of scope (in this story)
- Frontend prompt-selector dropdown (Story 15.3 consumes the library API).
- Real-fixture acceptance (Story 15.4).
- Writing the v2 prompt rubric body itself — that's part of Story 15.1's `CALL_TOPICS_V2_PROMPT_BODY` constant. Story 15.2 only wires it into the library.
