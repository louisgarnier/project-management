# Build Log — Call Tracker

### 2026-05-20 — EPIC-16: Project Updates RAG Rework (in progress / pending manual validation)

**Goal:** Replace auto-LLM merge in `project_updates` with 3 user-driven, citation-grounded verification passes against raw transcripts.

**Backend:**
- Migration 030: 6 new cols on `calls` (verify_new/verify_not_discussed/extract_updates × status/cache) + 3 cols on `topic_updates` (citations, evidence_trail, needs_manual_review) + soft-deprecate 3 old workflow library entries.
- `backend/prompts/{verify_new_topic,verify_not_discussed,extract_topic_updates}.py` — 3 new workflow prompt bodies (strict citation contract, transcripts as single ground truth).
- `backend/library/seed.py` — register 3 new system seeded_by_default entries; soft-deprecate `project_topics`, `merge_verification`, `not_discussed_check` (is_system=false, seeded_by_default=false).
- `backend/services/citation_verify.py` — `verify_citations` (verbatim-quote check) + `find_quote_lines` (post-hoc line-range computation).
- `backend/services/topic_verification.py` — orchestration for 3 passes: `run_verify_new`, `run_verify_not_discussed`, `run_extract_topic_updates`. Each has citation post-verify + 1 retry + `needs_manual_review` flag on second failure.
- `backend/services/topics_service.py` — added `_resolve_workflow_llm_for_category` helper (artifact_types → projects → system_settings → openrouter); extended `TopicIn`/`TopicUpdate` Pydantic models with `citations`, `evidence_trail`, `needs_manual_review`; `_persist_topic_update` + `save_topics` write the 3 new fields; `validate_project_updates` consumes `extract_updates_cache`; `rollback_to_stage` clears RAG caches when rolling past project_updates.
- DELETED: `run_merge_preview`, `_verify_merged_topics`, `verify_not_discussed_topics` (old), `run_verification_background`, `/merge-preview` endpoint, BackgroundTask trigger from `save_match_groups`.
- 3 new endpoints on `backend/routers/topics.py`: POST `/verify-new`, POST `/verify-not-discussed` (replaces old at same path), POST `/extract-updates`. All fire BackgroundTask + write to `calls.{*_cache, *_status}`.

**Frontend:**
- `frontend/src/types/index.ts` — `Citation`, `EvidenceTrailEntry`, `VerifyNewResult`, `VerifyNotDiscussedResult`, `ExtractedSnapshot`, `ExtractedUpdateResult`, `RagPassStatus`; `Call` interface extended with 6 cache/status fields; `TopicData` extended with citations/evidence_trail/needs_manual_review.
- `frontend/src/api/client.ts` — `verifyNew`, `verifyNotDiscussed`, `extractUpdates` methods; `mergePreview` replaced by deprecated stub (throws).
- `frontend/src/components/EvidenceTrail.tsx` — chronological citation strip (grouped by call, with verbatim quote + action label per entry).
- `frontend/src/components/TopicCitationBadge.tsx` — clickable `→ Call X cit-Y` tag that scroll-anchors to the trail.
- `frontend/src/components/ProjectUpdatesStage.tsx` — FULL REWRITE. 3-section sequenced-buttons layout (① Verify new → ② Verify not discussed → ③ Extract updates). No auto-trigger of any LLM on mount. Polling for each pass status field after click. Sections show side-by-side previous/this-call for merged topics until extraction runs. Topics migrate between sections based on ①/② verdicts. Save & Continue disabled until all 3 ✓ done.
- `frontend/src/components/TopicsTimeline.tsx` — ⚠️ icon on cells where `needs_manual_review=true`.
- `backend/services/topics_service.py::list_topics_timeline` — SELECT + return `needs_manual_review` per cell.

**Commits (12):** `08e3e88`, `78940f4`, `1431832`, `d076eebd`, `3b5d57e`, `d208b39`, `4849414`, `590529a`, `caf86ad`, `9f27021`, `fdcd52a`, `7a08785`.

**Tests:** 14 new + 3 obsolete deleted = 261 backend passed total (was 247 pre-EPIC-16); frontend tsc clean, eslint clean.

**Migration #030:** must be applied manually via Supabase Dashboard before backend restart.

**Manual smoke pending:** see `docs/project/config/2026-05-20-epic-16-manual-tests.md` (scenarios A, B, C + rollback).

**Known follow-ups:**
- `run_merge_background` left in topics_service.py as dead code (referenced now-deleted functions; no callers). Safe to delete in a follow-up.
- `TopicEvidenceDrawer.tsx` doesn't exist anymore (deleted EPIC-15 Story 15.3); evidence_trail rendering is wired into `MergedTopicCard` instead.
- `mergePreview` stub remains in client.ts as a defensive guard; can be removed once all callers are gone.
- Per-project artifact_types backfill (Tier-1 prompts for new categories) hasn't been done. Existing projects need a one-shot `seed_defaults` re-run OR migration to insert the 3 new categories into their artifact_types row. Without this, the resolution chain falls back to project default_llm.

---

## Open follow-ups (Phase 3 candidates)

- **2026-05-19 — pre-existing merge-prompt bug** (`backend/services/topics_service.py:1071-1080`, `1133-1142`): `call_excerpts_parts` builder in 1:1 and M:N merge paths still iterates `m.get("follow_up_items")` (always empty under EPIC-15 new shape) and renders `m.get("decisions")` as `f"  - {d}"` where `d` is now a dict — produces literal `{'id': ..., 'text': '...'}` strings in the merge prompt, degrading merge quality silently. Pre-existing — predates Story 15.5. Fix during Story 15.7 alongside the chronology+RAG plumbing rewrite.

### 2026-05-19 — EPIC-15 Phase 2 / Story 15.5: Call-topics extension (open_questions + decisions)

**Backend:**
- Migration 027: 4 new cols on topic_updates (open_questions+decisions JSONB, chronology_narrative+rag_verification_note TEXT) + demoted v2 library entry's seeded_by_default flag (with is_system=true guard).
- `backend/prompts/call_topics.py` — added `CALL_TOPICS_V3_PROMPT_BODY` with 3-array output + DUAL-CLASSIFY rule + decisions[] anti-hallucination guard + worked example.
- `backend/services/topics_service.py` — `_TOPIC_SCHEMA` + `_validate_topic` extended (at-least-one-of-three rule replaces tasks>=1); `_stamp_task_ids` → `_stamp_item_ids` (signature now takes call_id, stamps id + added_in_call_id across all 3 arrays, deepcopy + `is None` guards); `_persist_topic_update` writes new columns; structured log line includes open_questions+decisions counts.
- `backend/routers/topics.py` — `TopicPatch` + `patch_topic` accept open_questions + decisions partial fields (single SELECT call_id shared across all 3 stamping paths).
- `backend/routers/artifacts.py` — legacy SELECT fixed (was referencing dropped follow_up_items/owner under migration 026); sentiment restored after T7 polish.
- `backend/services/topic_lineage.py` — `get_lineage_topic_updates` SELECT updated; `build_lineage_evidence_block` rendering adapts decisions to .text + tasks to .task with defensive isinstance guard.
- Read-path sweep across 6+ topic_updates SELECTs in topics_service.py + topic_lineage.py + artifacts.py.

**Frontend:**
- `frontend/src/types/index.ts` — `OpenQuestionData` + `DecisionData` interfaces; `TaskData` lifecycle fields; `TopicData.decisions` + `open_questions` widened to `(string | …)[]` unions for back-compat; `TimelineCell.decisions` + `open_questions` widened too.
- `frontend/src/components/CallTopicsStage.tsx` — restructured from flat task table → per-topic block layout with 3 stacked sub-sections (Tasks / Open questions amber #fff8e6 / Decisions pale-green #f1f8ee). Inline edit on blur (text) + onChange (selects). + Add buttons stamp UUIDs client-side. Counter shows N topics · M tasks · X open questions · Y decisions.
- `frontend/src/components/CallTopicsHistoricalView.tsx` + `frontend/src/components/TopicsPanel.tsx` + `frontend/src/components/TopicsTimeline.tsx` — `.text` adapters added for legacy `string[]` back-compat.
- `frontend/src/api/client.ts` — `topicsAPI.patch` TS body type extended.

**Commits:** ~15 `[EPIC-15] story 15.5 …` commits (initial implementation + polish per code-review feedback per task).
**Tests:** 13+ new backend tests in test_topics_service.py (validator + stamping + persistence + PATCH); full suite green (247 passed, 13 skipped); tsc + lint clean.
**Migration:** 027 (manual, Supabase Dashboard) — required before backend restart.
**Manual smoke pending:** User browser test of the new 3-section UI on Call Topics stage.

**Known follow-ups (deferred to Story 15.7 / Phase 3):**
- Pre-existing merge-prompt builder bug in topics_service.py:1071-1080 + 1133-1142 (renders decisions dicts as literals under new shape) — logged in "Open follow-ups" section.
- Story 15.4 (matching UI read-only + real-fixture + rollback non-reg) — deferred to Phase 3, opens after Phase 2 closes.

---

## Current Stage
**EPIC-12 — Artifacts Overhaul (delivered 2026-04-23).** Last delivered epic. No active epic.

---

### 2026-04-23 — EPIC-12: Artifacts Overhaul

**Backend — schema:**
- Migration 021: `artifact_types` gets `kind TEXT` (CHECK llm/template/hybrid), `template_id TEXT`, `library_ref_id UUID` + FK. New `artifact_library` table with 11 columns.

**Backend — templates + library:**
- `backend/templates/` package: 5 renderers (next_steps, questions_list, agenda_skeleton, risk_register, decisions_digest) + `registry.py`.
- `backend/library/seed.py` — `SYSTEM_LIBRARY` 8 canonical entries + idempotent `upsert_system_library`.
- Startup hook in `main.py::lifespan` seeds library on boot.
- `backend/services/template_service.py` — dispatches artifact_types rows to renderers by `template_id`.

**Backend — library API:**
- `routers/library.py`: GET / POST / PATCH / DELETE /api/library + POST /reset-system. System entries can't hard-delete; reset re-applies SYSTEM_LIBRARY.

**Backend — artifact_types API:**
- Pydantic models carry `kind`, `template_id`, `library_ref_id`.
- 4 new endpoints: `from-library`, `library-source` (with name-fallback), `publish-to-library` (LLM kind only), `preview`.
- `seed_defaults` rewritten to read from `artifact_library` where `seeded_by_default=true` → new projects get 4 Tier-1 + 3 Tier-2 rows.

**Backend — generation flow:**
- `routers/artifacts.py::gen_one` forks on `kind`: template = render-only (no LLM); hybrid = 2 short LLM calls + render; llm = unchanged.

**Frontend — foundation:**
- `ArtifactKind`, `LibraryEntry` types + `MODEL_COSTS` map + `estimateCost()` helper.

**Frontend — artifacts page:**
- Two-tier layout: Tier 1 ⚙️ Workflow Prompts + Tier 2 📝 Artifact Prompts with labeled sections and descriptions.
- Workflow prompts filter fixed to include `merge_verification` + `not_discussed_check` (previously hidden).
- `ArtifactTypeCard` kind-conditional body: template = description + Preview; hybrid = intro/closing prompts + shared provider; llm = existing + diff badge + cost preview + Publish button.

**Frontend — library:**
- `/library` top-level page with System / Yours sections, `LibraryEntryCard` with inline edit/delete, "Reset system to defaults" button.
- `AddArtifactTypeModal` 3rd tab "Browse library" (new default).
- `PublishToLibraryDialog` wired into artifact card.
- Sidebar "📚 Artifact Library" nav entry.

**Commits:** 14 `[EPIC-12]` commits.
**Tests:** 32+ new backend tests. Frontend `tsc --noEmit` + `npm run lint` clean.
**Manual test doc:** `docs/project/config/2026-04-23-epic-12-manual-tests.md` — 6-phase walkthrough.
**Migration:** 021 (manual, Supabase) + startup hook seeds library idempotently.

---

**EPIC-11 — Call Topics Extraction Overhaul — code complete 2026-04-22 (pending manual validation)**
- All 6 stories done. Rubric-driven prompt, 4 new topic fields, OpenRouter provider, enriched tile UI, and model picker shipped.

---

### 2026-04-22 — EPIC-11: Call Topics Extraction Overhaul

**Backend — prompt lifecycle:**
- New `backend/prompts/` package with single-source-of-truth constants for all 4 workflow prompts (`call_topics`, `project_topics`, `merge_verification`, `not_discussed_check`) + `artifacts` bundle.
- `CALL_TOPICS_DEFAULT_PROMPT` — new multi-section prompt (ROLE + RUBRIC + ANCHORS + FEW-SHOT + PROCESS) encoding the 3-of-4 rubric, splits/filters, parked items, 3 anchor types, and importance scoring.
- Migration script `backend/scripts/migrate_call_topics_prompt.py` — replaces old-default prompts with new; preserves customized rows.
- `GET /api/artifact-types/defaults/{category}` endpoint powers "Reset to default" button.

**Backend — schema:**
- Migration 019: `topic_updates` gets `open_questions JSONB`, `is_parked BOOL`, `importance TEXT`, `rationale TEXT`. `artifact_types.model TEXT`, `projects.default_model TEXT`.
- `TopicIn` / `TopicOut` Pydantic models carry the 4 new fields with sensible defaults.
- `_TOPIC_SCHEMA` describes the full new payload shape.

**Backend — OpenRouter:**
- 5th LLM provider via `AsyncOpenAI` + `https://openrouter.ai/api/v1`.
- `generate_artifact(llm, *, model=None)` and `call_llm_raw(llm, *, model=None)` — model required when `llm='openrouter'`.
- `artifact_types.model` + `projects.default_model` propagate through create/update APIs, `extract_call_topics`, `run_merge_preview`, `_verify_merged_topics`, `verify_not_discussed_topics`, and `routers/artifacts.py` call sites.
- New projects seed `call_topics`, `merge_verification`, `not_discussed_check`, and all artifact types with OpenRouter + recommended model (per spec §4.4.4 table).

**Frontend — tile rewrite:**
- `CallTopicsStage.TopicRow` — 3 colour-coded sections (Decisions=grey, Actions=amber, Open questions=blue), importance dot + rationale tooltip, parked variant (⏸ chip, muted border, Un-park button), expand-to-edit affordances inline.
- `SectionBlock` reusable component for the three anchor sections.
- Ripple: `TopicEditor`, `TopicsDashboard`, `TopicsPanel`, `TopicEvidenceDrawer` render `open_questions` + surface `is_parked`.

**Frontend — model picker + prompt editor:**
- `MODEL_RECOMMENDATIONS` curated per category + `PROVIDER_LABELS`.
- `ArtifactTypeCard` — Provider dropdown (6 options), conditional Model dropdown, Custom slug input, expandable textarea (120px ↔ 500px), "Show runtime context" disclosure, "Reset to default" button.
- Project settings page (`/projects/{id}/artifacts`) — Provider + Model controls for `default_llm` / `default_model`.
- `ArtifactSelector` label appends model slug when effective provider is OpenRouter.

**Commits:** 13 `[EPIC-11]` commits landing the 14 plan tasks.
**Tests:** 17 new backend tests; full suite passes (155 passed) minus 4 pre-existing failures. Frontend `tsc --noEmit` + `npm run lint` clean (0 errors, 6 pre-existing warnings).
**Manual test doc:** `docs/project/config/2026-04-22-epic-11-manual-tests.md` — 5-phase walkthrough covering env setup, UI smoke, live extraction, quality spot-check, ripple surfaces.
**Migration:** 019 (manual, Supabase dashboard) + `backend/scripts/migrate_call_topics_prompt.py` (one-shot, preserves customized rows).

---

### 2026-04-21 — EPIC-10: Topic Lineage + Full-Stage Traceability + Prompt Quality — COMPLETE (2026-04-21)**
- All 9 stories done. Full Kanban-wide evidence traceability + Timeline item provenance & ancestor visualization shipped.

---

### 2026-04-21 — EPIC-10: Story 10.9 — Timeline Provenance + Ancestor Visualization

**Backend** — `list_topics_timeline` now returns `ancestor_topic_ids` on merge-result topics (ordered by ancestor's first_raised_call_id) and `merge_call_id` on archived topics. New backend regression test: `test_timeline_returns_ancestor_topic_ids_and_merge_call_id`.

**Frontend:**
- `frontend/src/utils/callColors.ts` — shared 8-color pastel palette (extracted from TopicEvidenceDrawer).
- `frontend/src/utils/provenance.ts` — pure `resolveProvenance` utility; exact-string match of current items against topic's per-call history, returning origin call_id or null. Standalone test script at `provenance.test.ts` runnable via `npx tsx`.
- `frontend/src/components/ProvenancePill.tsx` — compact pill showing `C{n}` with tooltip = full call title; muted `?` fallback when origin not matched.
- `TopicEvidenceDrawer.tsx` — follow-ups and decisions in per-call cards render with ProvenancePill.
- `TopicsTimeline.tsx` — chevron per merge-result row toggles indented ancestor rows (tree connectors, strikethrough, "merged ↗" badges on the merge-call cell, "(archived)" on later cells). "Show archived" toggle replaced with "Expand all lineage" / "Collapse all lineage". Cell expanded views render items with pills; collapsed summaries show unique origin-call set (e.g., "4 follow-ups (C1, C2)").

**Commits (8):** `8cf313d` (Task 1), `0d14ee1` (Task 2), `d5d33a6` (Task 3), `0fa7f70` (Task 4), `78bd6ff` (Task 5), `df5d784` (Task 6), `d82988f` (Task 7), `10a86e4` (Task 8). All `[EPIC-10]` prefix.

**Tests:** 54/54 backend tests PASS; standalone provenance tests 5/5 PASS; `npx tsc --noEmit` clean. Manual smoke pending user validation.

---

### 2026-04-21 — EPIC-10: Stories 10.2 through 10.8 + ERR-004

**ERR-004 side fix** (`d6773de`): promote-not-discussed persisted via ptid-only match group (`POST /api/calls/{id}/topics/promote-not-discussed`); survives re-merge and page refresh.

**Story 10.2 — Prompts audit** (`6c39d88`): `docs/project/config/epic-10-prompts-audit.md` covering 5 LLM prompts (extraction, per-topic merge, merge verification, not-discussed verification, artifacts) with file/line refs, blindnesses, and prioritised recommendations.

**Story 10.3 — Topic Evidence API** (`716bc08`): `GET /api/topics/{id}/evidence` returns ancestor-aware per-call trail (lineage nodes + calls with excerpt/summary/follow-ups/decisions/raw_extract/match_group/verification). 6 new backend tests.

**Story 10.4 — Evidence Drawer (lineage mode)** (`a8e78d9`): new `TopicEvidenceDrawer.tsx` — full-overlay drawer rendering per-call color-coded cards (8-pastel palette), lineage chip for merged topics, provenance badges on ancestor-source cards, collapsible raw_extract/match_group/verification. Mounted on Project Updates ("View evidence" per Updated Topic row) + Topics Timeline (click topic name).

**Story 10.5 — "+ new (merged)" label** (`a2b39b0`): backend returns `has_sources` + `source_names[]` on timeline topics; frontend renders merge-result cells in purple with tooltip listing source names. 1 new backend test.

**Story 10.6 — Prompt fixes from audit** (`8e68c3e`, `fd45fc4`, `ecce0ed`, `c3c9b43`):
- Fix 6.1 — extraction prompt receives existing project topic names as vocabulary hint (not Call 1)
- Fix 6.4 — merge verification now consumes `build_lineage_evidence_block` for ancestor evidence + dropped `transcript[:8000]` truncation
- Fix 6.5 — new `get_project_topics_lineage_context` for project-scope artifacts; per-call evolution visible
- 5 new backend tests + 1 pre-existing test repaired; audit doc updated with implemented/deferred status per prompt

**Story 10.7 — Call Topics evidence drawer** (`21ec689`): `TopicEvidenceDrawer` gained `mode="call_topic"` rendering a single-panel view of pending_topic data (transcript_excerpt + summary + follow-ups + decisions). Added `transcript_excerpt?` to the `TopicData` type. Mounted on Call Topics stage via "Show source" link per row. No fetch — uses inline pending data.

**Story 10.8 — Project Matching side-by-side drawer** (`206ec22`): `TopicEvidenceDrawer` gained `mode="matching"` — two-column grid with existing topic lineage (left) + current call extraction (right), kind-driven empty states, footer strip explaining the classification ("followed up" / "new" / "not discussed"). Mounted on Project Matching stage via "Show evidence" link on every row in both panes. No backend changes — reuses in-component state.

**Test status:** 52/52 topics+lineage+evidence tests green; 129/133 full suite (4 known pre-existing failures unrelated to Epic 10).

---

### 2026-04-20 — EPIC-10: Story 10.1 — Lineage Helper + Merge-Prompt Fix

### 2026-04-20 — EPIC-10: Story 10.1 — Lineage Helper + Merge-Prompt Fix

**New module: `backend/services/topic_lineage.py`** — walks `merged_into_topic_id` backwards to assemble ancestor-aware per-topic history. Four functions:
- `get_topic_lineage(topic_id, db)` — BFS from topic, returns self + ancestors
- `get_lineage_topic_updates(topic_id, db)` — returns every `topic_updates` row across the lineage, enriched with `source_topic_id`, `source_topic_name`, `call_title`, ordered by `created_at`
- `get_lineage_match_groups(topic_id, db)` — returns `topic_match_groups` rows where `project_topic_ids` intersects the lineage
- `build_lineage_evidence_block(topic_name, topic_id, db)` — renders the per-call evidence text block used by merge prompts, with a `(from archived topic: {name})` provenance line when evidence came from an archived ancestor

**Wired into `backend/services/topics_service.py`:** the nested `_load_transcript_excerpts` and `_build_excerpt_context` in `run_merge_preview` are gone; both merge paths (1:1 and M:N) now call `build_lineage_evidence_block`. Merges at any call depth now see evidence from archived ancestor topics — fixes the M:N "merge blindness" bug identified during Epic 9 testing.

**Observability:** `db_logger.info("🧬 [Lineage] Evidence for topic {id} ({name}) includes {N} ancestor(s): [...]")` fires when ancestor evidence contributed to a merge — check `logs/backend_*.log` during live merges.

**Tests:** 9 tests in `backend/tests/test_topic_lineage.py` covering linear history, M:N fan-in, multi-level chain, cycle guard, chronology, provenance, fallback, match-group filtering, and end-to-end Call-3-sees-Call-1 integration. Zero regressions on the 28 existing `test_topics.py` tests.

**Commits:** `026c736`, `4958152`, `f0cfcee`, `e460d87`, `e4f9a49`, `dbabdb1`, `3ec14cd`, `99022bc`.

---

### 2026-04-13 — EPIC-6: Stories 6.1 + 6.2 — Topics API + Topics UI

**Story 6.1: Topics API (backend)**
- `backend/database/migrations/002_topics_schema.sql` — alters topics table: drops old `status` column, adds `calls_open INT`, `archived BOOL`; alters topic_updates: adds `decisions JSONB`, `status TEXT`, `owner TEXT`, `sentiment TEXT` — **must be run manually in Supabase dashboard**
- `backend/services/topics_service.py` — `TopicIn`, `TopicUpdate`, `TopicOut`, `BriefItem`, `BriefOut` Pydantic models; `extract_topics(call_id)` — regular fn returning coroutine (allows MagicMock in tests); Call 1 flat extraction, Call 2+ three-bucket (followed_up/not_discussed/new_topics); `save_topics(call_id, topics)` — upserts topic_updates, increments/resets calls_open; `validate_call(call_id)` — uses `_get_previous_topics()` to check latest status, raises ValueError with unacknowledged topic IDs; `generate_brief(call_id)` — priority/decisions/watch_list; `list_project_topics(project_id)`
- `backend/routers/topics.py` — 5 endpoints: POST /extract, POST /topics, POST /validate (422 on unacknowledged), GET /brief, GET /projects/{id}/topics
- `backend/main.py` — topics router registered
- `backend/tests/test_topics.py` — 9 tests (models + router); 86 total backend tests passing

**Story 6.2: Topics UI (frontend)**
- `frontend/src/types/index.ts` — replaced stale Topic types with: `TopicStatus`, `TopicOwner`, `TopicSentiment`, `TopicDisposition`, `TopicData`, `ExtractionResult`, `BriefItem`, `CallBrief`, `TopicSavePayload`
- `frontend/src/api/client.ts` — added `topicsAPI` (extract, save, validate, brief, listForProject)
- `frontend/src/components/PreCallBrief.tsx` — collapsible; lazy-loads `GET /brief` only on first open (NFR-08); shows priority topics / decisions to confirm / watch list; staleness badges; empty state
- `frontend/src/components/TopicEditor.tsx` — inline editable topic row; all 9 fields; decisions append-only; staleness badge when calls_open ≥ 2; disposition buttons (Keep as-is / Archive) for not_discussed bucket
- `frontend/src/components/AddTopicForm.tsx` — collapsed "+ Add topic" button; inline form with name/summary/status/owner/sentiment
- `frontend/src/components/TopicsStage.tsx` — state machine (choice/extracting/reviewing/manual/validating); three-bucket view for Call 2+, flat list for Call 1; ActionBar with disabled Validate until dispositions set; error states for extract and validate
- `frontend/src/components/TopicsDashboard.tsx` — table view; filter by status (All/Open/In Progress/Resolved); "Stale first" toggle; resolved rows at opacity 0.6; staleness badge when calls_open ≥ 2
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — TopicsStage wired for topics stage; green "Call complete" banner for done stage
- `frontend/app/projects/[id]/board/page.tsx` — Topics tab renders TopicsDashboard; board page reads `?tab=topics` query param to activate tab
- `frontend/app/projects/[id]/topics/page.tsx` — redirect shim to `/projects/{id}/board?tab=topics`

**Key decisions:**
- `_get_previous_topics()` helper reused across extract/validate/brief/list — single source of truth for "latest status per topic"
- `extract_topics` is a regular function returning a coroutine (not `async def`) to allow `MagicMock` in unit tests
- Three-bucket view gated on `call_number > 1` from extraction response — no separate DB query for call number
- `canValidate` gate: `topics.length > 0 && unacknowledgedCount === 0` — enforces disposition on all not_discussed topics
- Board tab query param uses `window.location.search` on mount (avoids Next.js `useSearchParams` + Suspense requirement)

---

## Session History

### 2026-04-12 — EPIC-6: Multi-LLM Support

**Feature: Multi-LLM Provider Selection**
- `backend/services/llm_service.py` — `generate_artifact(prompt_used, transcript, llm: str) → str`; dispatches to Groq (`llama-3.3-70b-versatile`), Claude (`claude-sonnet-4-6`), or OpenAI (`gpt-4o`); 3-retry exponential backoff on rate limit errors; API keys from `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`
- `backend/database/migrations/004_multi_llm.sql` — adds `default_llm TEXT` to `projects` table (default `'claude'`); adds `llm TEXT` to `artifact_types` table (nullable — null = inherit project default)
- `backend/routers/projects.py` — added `GET /api/projects/{project_id}` (single project) and `PATCH /api/projects/{project_id}` (update `default_llm`)
- `backend/routers/artifact_types.py` — `llm` field exposed on all read/write endpoints; nullable (null = inherit project default)
- `backend/routers/artifacts.py` — `POST /api/calls/{call_id}/artifacts` now accepts `llm` per selection; stream endpoint resolves effective LLM (artifact override → project default) and passes to `llm_service.generate_artifact`
- `backend/tests/test_llm_service.py` — 4 new tests: all three providers dispatch correctly, unknown provider raises ValueError
- `frontend/src/types/index.ts` — `default_llm` added to `Project`; `llm` (nullable) added to `ArtifactType`
- `frontend/src/api/client.ts` — `projectsAPI.get`, `projectsAPI.updateDefaultLlm`; `artifactTypesAPI` updated to include `llm` on create/update; `artifactsAPI.createSelections` accepts per-artifact `llm`
- `frontend/app/projects/[id]/artifacts/page.tsx` — per-artifact-type LLM dropdown; apply-to-all control
- `frontend/src/components/ArtifactTypeCard.tsx` — shows/edits `llm` field with inherit-project-default option
- `frontend/src/components/ArtifactSelector.tsx` — per-artifact LLM dropdown in generation flow; inherits project default when not set
- `frontend/src/components/ArtifactsStage.tsx` — passes resolved LLM per artifact to `createSelections`; apply-to-all LLM control in selection phase

**Files deleted:** `backend/services/claude_service.py` (replaced by `llm_service.py`)

**Tests:** 70 backend tests passing (4 new `test_llm_service` + 2 new artifacts + 2 new artifact_types + 4 new projects)

**Key decisions:**
- `llm` on `artifact_types` is nullable; null means "use project default" — not stored as a string
- Provider dispatch in `llm_service.py` uses a single `if/elif` — no dynamic import or registry
- `GROQ_API_KEY` uses `AsyncOpenAI` with `base_url=https://api.groq.com/openai/v1` (Groq is OpenAI-compatible)
- Apply-to-all sets all artifact type LLMs in state but does not persist unless user saves individually

---

### 2026-04-12 — EPIC-5: Story 5.4 — Artifacts Stage UI

**Story 5.4: Artifacts Stage UI**
- `backend/routers/artifacts.py` — added `GET /api/calls/{call_id}/artifacts` (list, 404 guard) and `PATCH /api/artifacts/{artifact_id}` (update content/status; 422 no-fields, 404 not-found); `ArtifactUpdate` Pydantic model
- `backend/tests/test_artifacts.py` — 5 new tests: list happy path, patch happy path, list 404, patch 422, patch 404 (58 total backend tests passing)
- `frontend/app/api/sse/[...path]/route.ts` — dedicated SSE proxy; passes `backendResponse.body` directly without buffering (unlike the JSON proxy); headers: `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- `frontend/src/api/client.ts` — added `artifactsAPI` (createSelections, list, update); added `callsAPI.advanceStage`; added `Artifact` to type imports
- `frontend/src/components/ArtifactSelector.tsx` — per-type row: Generate via Claude / Manual / Skip toggle buttons; exports `ArtifactMode` type
- `frontend/src/components/ArtifactCard.tsx` — status badge (pending/generating/done/error), spinner during generation, editable textarea, Mark Done button, inline `StatusBadge`
- `frontend/src/components/ArtifactsStage.tsx` — three-phase orchestrator: select → generating → reviewing; SSE consumption via ReadableStream + line buffer; `AbortController` cleanup on unmount; skips to reviewing if artifacts already exist
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — replaced "coming soon" placeholder with `ArtifactsStage` for artifacts stage; other past-transcript stages still show placeholder

**Key decisions:**
- SSE streams through `/api/sse/` not `/api/proxy/` (proxy buffers response.json())
- `streamArtifacts()` takes no arguments — uses closured `callId` from component scope
- `handleRetry` accepts `_artifactId` to match `ArtifactCard` prop type but re-streams all pending artifacts
- `ArtifactUpdate` filter uses `if v is not None` (not falsiness) — allows `content: ""` correctly

### 2026-04-12 — EPIC-5: Story 5.3 — Claude Service & SSE

**Story 5.3: Claude Service & SSE Endpoint**
- `backend/services/claude_service.py` — `generate_artifact(prompt_used, transcript) → str`; uses `AsyncAnthropic`, model `claude-sonnet-4-6`, 4 total attempts (3 retries) with exponential backoff (1s/2s/4s) on 429; logs start, token counts, errors
- `backend/routers/artifacts.py` — two endpoints:
  - `POST /api/calls/{call_id}/artifacts` — accepts `[{artifact_type_id, mode}]`; snapshots `prompt_used` from artifact type at creation; mode='manual' → status='done'; mode='claude' → status='pending'; 404 guard for call
  - `GET /api/calls/{call_id}/artifacts/stream` — SSE StreamingResponse; parallel generation via asyncio tasks + queue; emits `status`(generating) → `done`/`error` per artifact, `complete` at end; Cache-Control + X-Accel-Buffering headers
- `backend/tests/test_artifacts.py` — 5 tests; 53 total backend tests pass
- `backend/main.py` — artifacts router registered
- Plan: `docs/project/config/2026-04-12-story-5.3-claude-service-plan.md`

**Key decisions:**
- `prompt_used` is snapshotted at POST time — artifact type edits never affect generated history
- One artifact error does not block others (independent asyncio tasks, broad except)
- `Literal["claude", "manual"]` on mode field — invalid modes rejected with 422
- Supabase singleton client safe for concurrent coroutine use (each `.table()` creates independent query builder)

### 2026-04-12 — EPIC-5: Stories 5.1 + 5.2 — Artifacts Tab UI + API

**Story 5.1: Artifacts Tab UI**
- `frontend/app/projects/[id]/artifacts/page.tsx` — Artifacts page: load/error/empty states, delete/update handlers, modal trigger
- `frontend/src/components/ArtifactTypeCard.tsx` — expandable card: Default/Custom badge, expand/collapse prompt, inline edit (name + textarea), delete with confirm dialog, orange border on edit
- `frontend/src/components/AddArtifactTypeModal.tsx` — two-mode modal: Create new (name + prompt) + Import from another project (project dropdown → type checklist → multi-select confirm); error states for all API failures + retry
- `frontend/src/components/Sidebar.tsx` — added Artifacts (⚡) nav item between Board and Topics
- `frontend/src/types/index.ts` — added `project_id` to `ArtifactType`
- `frontend/src/api/client.ts` — `artifactTypesAPI`: list, create, update, delete, import

**Story 5.2: Artifact Types API**
- `backend/database/migrations/003_artifact_types_project_scoped.sql` — adds `project_id` FK (NOT NULL), clears old global seed rows
- `backend/routers/artifact_types.py` — GET, POST, PATCH, DELETE, POST /import; `seed_defaults()` exports 6 default types; 403 guard on default delete; import is intentionally cross-project
- `backend/tests/test_artifact_types.py` — 7 tests covering all endpoints and guards; 48 total backend tests pass
- `backend/routers/projects.py` — `seed_defaults(project["id"])` called after project creation
- `backend/main.py` — artifact_types router registered

**Key decisions:**
- artifact_types is project-scoped (project_id FK), not global
- Importing from another project creates independent copies (`is_default=False`)
- ArtifactTypeUpdate validates `min_length=1` to prevent empty-string writes
- Plan: `docs/project/config/2026-04-12-story-5.1-artifacts-tab-plan.md`

### 2026-04-10 — EPIC-4 closed: Story 4.6 + extras
**Story 4.6: Context File Attachments**
- Supabase Storage `call-files` bucket (manual setup)
- `backend/routers/files.py` — 4 endpoints: upload (multipart), list, delete, signed URL (60s TTL)
- `backend/tests/test_files.py` — 10 tests, all passing
- `frontend/src/types/index.ts` — `CallFile` interface
- `frontend/src/api/client.ts` — `proxyFetchForm`, `filesAPI` (upload, list, delete, downloadUrl), `callsAPI.resetTranscript`
- `frontend/src/components/ContextFiles.tsx` — upload + list + delete (editable) + download-only (readonly prop)
- `frontend/app/api/proxy/[...path]/route.ts` — multipart passthrough + 204 fix (`new NextResponse(null, {status:204})`)
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — ContextFiles wired in (readonly), reset transcript button for artifacts stage
- ADR-002 written for Supabase Storage adoption

**Extras built this session:**
- Delete project UI: `Sidebar.tsx` — "🗑 Delete project" button with confirm dialog, calls existing `DELETE /api/projects/{id}`
- Reset transcript: `DELETE /api/calls/{call_id}/transcript` (new backend endpoint) — rolls back artifacts → transcript, clears transcript + transcript_source via raw PATCH to bypass supabase-py None-filtering bug
- Transcript validate/review screen: `TranscriptStage.tsx` — after transcription, shows review screen with transcript preview + ContextFiles before advancing to Artifacts
- Time estimate calibration: formula `15 + 8s/MB` (was `20s/MB`); root cause was fixed 15s Metal JIT overhead per request
- Metal warmup: `transcription/transcribe.py` — `preload_model()` runs 0.5s silence dummy inference at startup to eliminate first-run latency spike

**Bug fixes:**
- 503 on delete project: `NextResponse.json(null, {status:204})` throws in Next.js → fixed to `new NextResponse(null, {status:204})`
- Transcript not cleared on reset: supabase-py silently drops `None` from `.update()` → fixed via `client.postgrest.session.patch()` with explicit `json.dumps()`

### 2026-04-10 — Story 4.8 (patch): Historical card UX fixes
- `CallCard.tsx` + `KanbanBoard.tsx` — historical badge shows column's stage label in green (was showing current stage in orange)
- `KanbanBoard.tsx` — historical card click appends `?view=${col.key}` to URL
- `TranscriptPanel.tsx` — added `defaultOpen` prop
- `calls/[call_id]/page.tsx` — `?view=transcript` renders transcript-only mode (no stage bar, panel expanded)

### 2026-04-10 — Story 4.8: Kanban History Trail + Persistent Transcript Panel
- `KanbanBoard.tsx` — column filter changed to show all calls that have reached or passed each stage; STAGE_INDEX map for O(1) lookups; projectId guard added
- `CallCard.tsx` — `isHistorical` prop: grey background + ✓ badge for historical cards; explicit `dimColor` in STAGE_CONFIG; `lineCount` memoized
- `TranscriptPanel.tsx` — new collapsible component: view/edit transcript via PATCH, download .txt; `savedText` state for accurate `isDirty`; robust download helper
- `calls/[call_id]/page.tsx` — TranscriptPanel wired in for all post-transcript stages

### 2026-04-10 — Story 4.7: Replace Transcription Engine with MLX Whisper
- Replaced openai-whisper + pyannote with mlx-whisper 0.4.3 (Apple Silicon Neural Engine)
- `transcription/transcribe.py` — rewritten: `preload_model()`, `transcribe_audio()` returns raw text (no timestamps/speaker labels)
- `transcription/main.py` — removed load_dotenv/Path, lifespan calls preload_model only
- `transcription/requirements.txt` — mlx-whisper==0.4.3, removed pyannote/openai-whisper/torchaudio
- `run_transcription.sh` — checks `import mlx_whisper`, rm -rf old venv before rebuild
- `transcription/.env` deleted, `.env.example` updated (no HF_TOKEN needed)
- 6/6 transcription tests pass, integration test confirmed raw text output

### 2026-04-10 — Story 4.5: Transcript Review, Edit & Download
- DB migration: `transcript_source TEXT` column added to `calls`
- `backend/routers/calls.py` — `POST /transcript` accepts `source_filename`, new `PATCH /transcript` endpoint (edit without stage change)
- 4 new tests, 31 total passing
- `frontend/src/types/index.ts` — `transcript_source: string | null` added to Call
- `frontend/src/api/client.ts` — `submitTranscript` accepts sourceFilename, added `updateTranscript`
- `frontend/src/components/TranscriptStage.tsx` — review step: upload → editable textarea → download/replace/save & continue
- `frontend/src/components/CallCard.tsx` — shows transcript line count + source filename

### 2026-04-09 — Story 4.4: Server Control UI
- `frontend/app/api/local/process.ts` — ChildProcess singleton (getServerProcess / setServerProcess)
- `frontend/app/api/local/start/route.ts` — POST: spawns run_transcription.sh, registers exit/error listeners
- `frontend/app/api/local/stop/route.ts` — POST: SIGTERM with try/catch guard
- `frontend/app/api/local/status/route.ts` — GET: health check + process-alive fallback → running / starting / offline
- `frontend/src/api/client.ts` — added `localServerAPI` (status, start, stop)
- `frontend/src/components/TranscriptionStatusBadge.tsx` — replaced with 4-state badge + Start/Stop buttons
- `frontend/src/components/TranscriptStage.tsx` — removed OfflineModal, inline error on offline MP3
- `frontend/src/components/OfflineModal.tsx` — deleted
- EPIC-4 closed — all 4 stories done

---

## Session History

### 2026-04-09 — Story 4.3: Transcript Stage UI
- `frontend/src/api/client.ts` — added `callsAPI.getCall`, `callsAPI.submitTranscript`, `transcriptionAPI` (health + transcribe, direct to localhost:8001)
- `frontend/src/components/TranscriptionStatusBadge.tsx` — polls health every 30s, green/orange badge
- `frontend/src/components/OfflineModal.tsx` — startup instructions, polls every 3s, auto-dismisses on server online
- `frontend/src/components/TranscriptStage.tsx` — MP3 and .txt file pickers, health check before MP3, uploading state + `beforeunload` guard, error state
- `frontend/app/projects/[id]/calls/[call_id]/page.tsx` — fetches call, stage progress bar, routes to TranscriptStage for transcript stage
- EPIC-4 closed — all 3 stories done

### 2026-04-09 — Story 4.2: Transcript Stage Backend
- `POST /api/calls/{call_id}/transcript` added to `backend/routers/calls.py`
- `TranscriptSubmit` Pydantic model: `transcript: str = Field(min_length=1)`
- Guards: 404 if call not found, 409 if not at transcript stage, 422 if empty string
- Single DB update: sets `transcript` + advances `kanban_stage` to `artifacts`
- `backend/tests/test_transcript.py` — 5 tests (happy path, exact text, 404, 409, 422)
- 27/27 backend tests passing

### 2026-04-09 — Story 4.1: Local Transcription Server
- `transcription/transcribe.py` — `get_whisper()`, `get_pipeline()` (with HF_TOKEN guard), `transcribe_audio(path, filename) → str`
- `transcription/main.py` — refactored to import from transcribe.py; lifespan preloads both models at startup; `/health` returns `{"status":"ok","models":"loaded"}`; `/transcribe` mp3-only, 422 for other types
- `transcription/tests/test_transcribe.py` — 4 tests: unit test for transcribe_audio + 3 API tests (health, mp3-only guard, formatted transcript)
- `transcription/tests/test_health.py` — updated to use fixture-based mocking (lifespan now loads models)
- `run_transcription.sh` — already existed, unchanged
- 28/28 tests passing (6 transcription + 22 backend)



### 2026-04-09 — Story 3.2: Kanban Board UI
- Live BoardPage fetching calls from GET /api/projects/{id}/calls
- KanbanBoard: 4 columns (Get Transcript / Artifacts / Topics / Done) with CallCard per call
- CallCard: colored left border, stage badge, date, hover shadow, done opacity 0.65
- NewCallModal: title input, POST on submit, reloads board on success
- "+ New Call" disabled with tooltip when active call exists (hasActiveCall guard)
- Placeholder call detail page at /projects/[id]/calls/[call_id]
- Tabs: Kanban (live) + Topics (placeholder)
- TypeScript clean, ESLint clean, Prettier clean

### 2026-04-09 — Story 3.1: Calls API
- Implemented GET /api/projects/{id}/calls, POST /api/projects/{id}/calls, GET /api/calls/{id}, PATCH /api/calls/{id}/stage
- 409 sequential enforcement: only one active call per project
- Stage transitions: transcript → artifacts → topics → done (422 on skip)
- 9 new tests, 22 total passing
- ruff + black clean

### 2026-04-09 — EPIC-1 wrap-up + next@15 upgrade
**Completed:** EPIC-1 (Stories 1.1, 1.2, 1.3) verified and closed
**Fixes applied:**
- ruff auto-fixed 10 import-sort errors in backend/
- Recreated `backend/.env.example` (had been deleted)
- Upgraded `next@16.0.3` (CVE) → `next@15.x` (stable, 0 vulnerabilities)
- Upgraded `eslint@8` → `eslint@9` (flat config via `@eslint/eslintrc` FlatCompat)
- Created `frontend/eslint.config.mjs` replacing `.eslintrc.json`
- Fixed `frontend/src/utils/logger.ts` — ternary-as-statement → if/else
- Logged upgrade as ADR-001

**Verification (all passing):**
- 8/8 backend tests pass
- ruff: 0 errors, black: 0 changes
- ESLint (frontend): 0 errors, 0 warnings

**Next session starts at:** EPIC-2 / Story 2.1 — Projects API

### 2026-04-09 — EPIC-2 / Story 2.1 — Projects API
**Completed:** Projects CRUD API
**Built:**
- `backend/routers/projects.py` — GET /api/projects, POST /api/projects, DELETE /api/projects/{id}
- `backend/main.py` — router registered with `/api` prefix
- `backend/tests/test_projects.py` — 5 tests (TDD, all passing)

**Verification:**
- 13/13 backend tests pass
- 404 on delete non-existent project (not 500)
- db_logger on every Supabase operation

**Next session starts at:** EPIC-2 / Story 2.2 — Project List UI

### 2026-04-09 — EPIC-2 / Story 2.2 — Project List UI
**Completed:** Project list, create modal, project detail placeholder
**Built:**
- `frontend/app/page.tsx` — fetches projects, shows list + create button
- `frontend/src/components/ProjectList.tsx` — list with empty state
- `frontend/src/components/CreateProjectModal.tsx` — form (name + description)
- `frontend/app/projects/[id]/page.tsx` — placeholder page
- `frontend/src/api/client.ts` — added `projectsAPI` (list, create, delete)

**Verification:**
- ESLint: 0 errors
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement

### 2026-04-09 — EPIC-2 / Story 2.3 — App Shell & Project List UI (Redesign)
**Completed:** Jira-like app shell — top nav, sidebar, per-project nav, placeholder pages
**Built:**
- `frontend/src/components/TopNav.tsx` — blue top nav (static server component)
- `frontend/src/components/Sidebar.tsx` — client component, project list + per-project nav, create modal, hash-stable colours, error logging
- `frontend/src/components/CallCard.tsx` — placeholder card component for EPIC-3
- `frontend/app/layout.tsx` — root layout with shell (TopNav + Sidebar + main)
- `frontend/app/page.tsx` — "select a project" landing
- `frontend/app/projects/[id]/page.tsx` — redirects to /board
- `frontend/app/projects/[id]/board/page.tsx` — 4-column kanban placeholder
- `frontend/app/projects/[id]/topics/page.tsx` — placeholder
- `frontend/app/projects/[id]/history/page.tsx` — placeholder
- Deleted `frontend/src/components/ProjectList.tsx`

**Verification:**
- ESLint: 0 errors, 0 warnings
- 13/13 backend tests still passing
- Manual browser test required before EPIC-3

**Next session starts at:** EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement
