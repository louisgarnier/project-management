# Story 11.3 — OpenRouter Provider + Model Propagation

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `done` — 2026-04-22
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §4.4
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Tasks 7–8

---

## Goal
Add OpenRouter as the 5th LLM provider (alongside Groq, DeepSeek, Claude, OpenAI) via the existing `AsyncOpenAI` pattern with a new `base_url`, and thread the `model` slug end-to-end: artifact type row → project default → `generate_artifact` call site.

## Acceptance Criteria
- [x] `generate_artifact(llm='openrouter', *, model=...)` dispatches to `https://openrouter.ai/api/v1` with the given slug; raises `ValueError` when model missing
- [x] `call_llm_raw(llm='openrouter', *, model=...)` behaves identically
- [x] `ArtifactTypeCreate` / `ArtifactTypeUpdate` accept `model: str | None`; persisted on create/update
- [x] `ProjectUpdate` accepts `default_model: str | None`; persisted on PATCH
- [x] `extract_call_topics` resolves effective model via artifact type → project default → None, passes to `_call_llm`
- [x] `routers/artifacts.py` resolves effective model and passes to `generate_artifact`
- [x] `OPENROUTER_API_KEY` documented in `backend/.env.example` and README
- [x] Tests: openrouter dispatch with base_url + model; openrouter without model raises; API round-trips on both artifact types and projects

## Tasks
Covers Plan Task 7 (llm_service dispatch), Task 8 (API propagation + call-site wiring).
