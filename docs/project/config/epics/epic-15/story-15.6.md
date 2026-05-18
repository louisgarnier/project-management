# Story 15.6 — `context_scope` 4-value Enum + Context-Assembly Seam

**Epic:** EPIC-15 — Call Topics Rebuild (Phase 2 / P2-B)
**Status:** [ ] todo
**Spec:** `docs/project/config/2026-05-18-epic-15-phase-2-architecture.md` §3, §4.1 (context-assembly seam), §4.2 (modal + types), §5
**PRD:** `docs/project/config/2026-05-18-epic-15-phase-2-prd.md` G4, G5, US-P2-03, FR-P2-05/06, Q4, Q6
**Approved mockup:** AddArtifactTypeModal dropdown — covered by existing modal layout; 4-option `<select>` only.
**Blocks:** — (parallel-safe with 15.5 / 15.7 / 15.8 per architecture §322)
**Depends on:** — (independent migration slice; coordinates with 15.5 on the shared migration 027)

## Goal
Replace today's 2-value `context_scope` (`call` / `project`) with a 4-value enum (`this_call_transcript`, `all_call_transcripts`, `this_call_topics`, `all_project_topics`). Wire a single context-assembly seam in `gen_one` so any LLM artifact prompt can request any of the 4 scopes. Migrate the existing 8 system library entries to explicit scopes (per Q4). Add a 4-option dropdown to the artifact-type creation modal.

## Acceptance Criteria

### Backend — migration + CHECK constraint
- [ ] `backend/database/migrations/027_epic15_phase2_schema.sql` applied (shared with 15.5):
  - [ ] UPDATE old `'call'` → `'this_call_topics'`, `'project'` → `'all_project_topics'` (bulk).
  - [ ] DROP + re-ADD `artifact_library_context_scope_check` with the 4 new values.
  - [ ] Explicit per-name migration (overrides bulk):
    - `Executive Summary`, `Email Summary (1-pager)`, `Email Follow-up (pre-next-call)`, `Next Steps & Action Items`, `Questions for Stakeholders`, `Decisions Digest` → `this_call_topics`
    - `Risk Register`, `Next Call Agenda` → `all_project_topics`
  - [ ] Tier-1 workflow-prompt entries (`call_topics`, `project_topics`, `merge_verification`, `not_discussed_check`) → `this_call_topics` (placeholder to satisfy CHECK; unused at runtime).

### Backend — context-assembly seam
- [ ] New helper in `backend/services/artifact_generation.py` (or wherever `gen_one` lives): `_assemble_context(scope, call_id, project_id, db) -> str`
  - [ ] `this_call_transcript` → return `calls.transcript` for `call_id`.
  - [ ] `all_call_transcripts` → concatenate every call's transcript in this project, **chronological**, labeled by call date. Includes the current call (Q6).
  - [ ] `this_call_topics` → render `list_call_topics(call_id)` as structured text including the 3 sections (tasks / open_questions / decisions).
  - [ ] `all_project_topics` → render `list_project_topics(project_id)` as structured text **including chronology cells** (chronology_narrative + rag_verification_note when present).
- [ ] `gen_one` calls `_assemble_context(artifact_type.context_scope, ...)` before invoking the LLM. The assembled context replaces today's hard-coded transcript-only or topics-only branches.
- [ ] Pydantic models for artifact_type create/update accept the 4-value enum; unknown values rejected with 422.

### Backend — seed updates
- [ ] `backend/library/seed.py::SYSTEM_LIBRARY`: every entry's `context_scope` matches the migration's explicit values above. `upsert_system_library` writes the 4-value scope on fresh installs.

### Frontend
- [ ] `frontend/src/types/index.ts`:
  - [ ] Add `ContextScope` type union (4 values).
  - [ ] Extend `LibraryEntry` with `context_scope: ContextScope`.
  - [ ] Extend `ArtifactType` with `context_scope: ContextScope`.
- [ ] `frontend/src/components/AddArtifactTypeModal.tsx`:
  - [ ] Add `<select>` for `context_scope` with 4 labelled options:
    - "This call's transcript" → `this_call_transcript`
    - "All call transcripts (chronological)" → `all_call_transcripts`
    - "This call's topics" → `this_call_topics`
    - "All project topics (incl. previous calls)" → `all_project_topics`
  - [ ] Default: `this_call_topics`.
  - [ ] Persists via existing artifact-type POST.
- [ ] `frontend/src/components/ArtifactTypeCard.tsx`: display + edit current context_scope value (4-option dropdown matching modal).

### Tests
- [ ] Backend: `_assemble_context` unit tests covering all 4 branches (mock db; verify the right rows/columns are read).
- [ ] Backend: `test_artifact_types.py` — POST/PATCH accepts each of the 4 values; rejects unknown values with 422.
- [ ] Backend: migration smoke — apply 027 on a fixture DB with old-shape `call`/`project` rows; confirm all rows end with one of the 4 new values.
- [ ] Frontend: `tsc --noEmit` + `eslint` clean.
- [ ] Manual: create one artifact-type per scope via modal; generate; confirm LLM receives the expected context (check structured log line).

## Out of scope (handled in other stories)
- The schema portion adding `open_questions` / `decisions` / chronology columns on `topic_updates` → Story 15.5 (same migration file).
- The 2 new system library entries `Chronology Narrative` + `RAG Verification` → Story 15.7.
- Rewrites of the 4 existing LLM artifact prompt bodies → out of scope per Q4 (trust context engine; revisit only if smoke reveals drops).
