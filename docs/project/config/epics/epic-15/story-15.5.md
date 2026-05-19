# Story 15.5 — Call-Topics Extension: `open_questions[]` + `decisions[]`

**Epic:** EPIC-15 — Call Topics Rebuild (Phase 2 / P2-A)
**Status:** [x] code-complete (2026-05-19) — awaiting user smoke + migration 027 manual run in Supabase Dashboard
**Spec:** `docs/project/config/2026-05-18-epic-15-phase-2-architecture.md` §3, §4.1, §4.2
**PRD:** `docs/project/config/2026-05-18-epic-15-phase-2-prd.md` G1, G2, G3, US-P2-01, US-P2-02
**Approved mockup:** `phase2-call-topics-extended.html` (Call Topics stage with 3 sections per topic)
**Blocks:** 15.7 (Project tracker state), 15.8 (xlsx exporter)

## Goal
Extend the v2 call_topics prompt to emit `open_questions[]` and `decisions[]` alongside `tasks[]` (single LLM round-trip). Migration 027 adds the two new JSONB columns + 2 chronology fields on `topic_updates`. Frontend renders 3 stacked sections per topic in the Call Topics stage. Sweep all read paths.

## Acceptance Criteria

### Backend — schema + prompt + service
- [ ] `backend/database/migrations/027_epic15_phase2_schema.sql` applied:
  - [ ] ADDS `topic_updates.open_questions JSONB NOT NULL DEFAULT '[]'::jsonb`
  - [ ] ADDS `topic_updates.decisions JSONB NOT NULL DEFAULT '[]'::jsonb`
  - [ ] ADDS `topic_updates.chronology_narrative TEXT`, `topic_updates.rag_verification_note TEXT` (used by Story 15.7 — fine to add here)
- [ ] `backend/prompts/call_topics.py` extended: `CALL_TOPICS_V3_PROMPT_BODY` (or evolved v2) adds two new sections to the rubric with examples and the DUAL-CLASSIFY rule. Old `CALL_TOPICS_V2_PROMPT_BODY` constant deleted; library entry seeded with v3.
- [ ] `backend/services/topics_service.py`:
  - [ ] `_TOPIC_SCHEMA` describes 6 top-level fields per topic: `name`, `importance`, `key_terms`, `evidence`, `tasks`, `open_questions`, `decisions`.
  - [ ] `_validate_topic` requires both new arrays as lists (empty allowed); validates inner item shape (open_questions: `{text, owner?, status?}`; decisions: `{text}`).
  - [ ] Item-stamping helper extended to stamp UUIDs + `added_in_call_id` on every item in tasks/open_questions/decisions arrays at persistence.
  - [ ] `_persist_topic_update` writes the 2 new arrays.
- [ ] `backend/library/seed.py`: `Call Topics — v3` entry added (or v2 entry updated in-place if same name). `seeded_by_default=true`. Old v2 demoted or replaced.
- [ ] Sweep every supabase SELECT against `topic_updates` to include `open_questions, decisions, chronology_narrative, rag_verification_note` (same drill as Phase 1 — see commit `6ecb7af` for the read-path sweep pattern).
- [ ] Structured log line extended: `📥 [CallTopics] ... topics_produced=N tasks=X open_questions=Y decisions=Z latency_ms=...`.

### Frontend
- [ ] `frontend/src/types/index.ts`:
  - [ ] Add `OpenQuestionData` + `DecisionData` interfaces (see architecture §4.2).
  - [ ] Extend `TopicData` with `open_questions: OpenQuestionData[]` + `decisions: DecisionData[]` + `chronology_narrative?: string` + `rag_verification_note?: string`.
- [ ] `frontend/src/components/CallTopicsStage.tsx`:
  - [ ] Renders 3 stacked sections per topic: Tasks (existing) → Open questions (NEW, amber tint `#fff8e6`) → Decisions (NEW, pale-green tint `#f1f8ee`). Per the approved mockup.
  - [ ] Open questions section: inline-editable list with text + owner (optional) + status dropdown + per-row × + `+ Add open question` button.
  - [ ] Decisions section: inline-editable list with text + per-row × + `+ Add decision` button (decisions have no status / no closure UX — they're immutable post-commit).
  - [ ] Header counter updated: `Extracted (N topics · M tasks · X open questions · Y decisions)`.
  - [ ] Empty section collapses gracefully (renders the muted "— no open questions / decisions" placeholder, doesn't bloat the row).
  - [ ] Persistence via PATCH `/api/topics/{id}` with `open_questions` / `decisions` partial fields.

### Tests
- [ ] `backend/tests/test_topics_service.py` extended:
  - [ ] `_validate_topic` accepts a topic with `open_questions=[]` + `decisions=[]` (empty) and a topic with populated arrays.
  - [ ] Items get UUIDs + `added_in_call_id` stamped at persistence.
  - [ ] Persistence payload writes only the new columns; legacy keys still absent.
- [ ] tsc + lint clean.
- [ ] Full backend suite green (only EPIC-15 legacy tests stay skipped from Phase 1).

## Out of scope (deferred to 15.6 / 15.7 / 15.8)
- `closed_in_call_id` lifecycle stamping on status flips → Story 15.7.
- Chronology narrative + RAG verification LLM generation → Story 15.7.
- `context_scope` enum + AddArtifactTypeModal dropdown → Story 15.6.
- xlsx exporter + ProjectTrackerTab → Story 15.8.
