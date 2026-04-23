# Story 12.3 — Artifact Types API + Generation Fork

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** pending
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §4.5, §4.6, §4.7
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Tasks 5–7

## Goal
Extend artifact_types Pydantic models + 4 new endpoints (from-library, library-source, publish-to-library, preview). Rewrite `seed_defaults` to read from `artifact_library` table. Fork the artifact generation flow in `stream_artifacts` to handle template + hybrid kinds.

## Acceptance Criteria
- [ ] `ArtifactTypeCreate` / `ArtifactTypeUpdate` carry `kind`, `template_id`, `library_ref_id` fields with appropriate defaults
- [ ] `POST /api/projects/{id}/artifact-types/from-library` copies a library entry to artifact_types with `library_ref_id` set
- [ ] `GET /api/artifact-types/{id}/library-source` returns linked entry OR name-fallback to system library; 404 when no match
- [ ] `POST /api/artifact-types/{id}/publish-to-library` creates user library entry, links source row; 400 for non-LLM kinds
- [ ] `POST /api/artifact-types/{id}/preview` renders template/hybrid for a given call_id; 400 on LLM kind
- [ ] `backend/services/template_service.py` dispatches artifact_type rows to the correct renderer via `template_id`
- [ ] `seed_defaults` rewritten to insert 4 Tier-1 workflow prompts + library entries where `seeded_by_default=true`
- [ ] Generation flow (`gen_one` in `routers/artifacts.py`) forks on `kind`: template skips LLM; hybrid calls LLM twice (intro + closing) + renders skeleton; llm unchanged
- [ ] Hybrid `prompt` column stores JSON `{intro, closing}`
- [ ] Test coverage: 4 API tests + seed_defaults test + generation fork verification

## Tasks
Covers Plan Task 5 (API extensions), Task 6 (seed_defaults rewrite), Task 7 (generation fork).
