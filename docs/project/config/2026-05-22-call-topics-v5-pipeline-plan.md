# Call Topics Pipeline v5 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-shot v4 call_topics extraction with a 13-stage pipeline where each LLM call performs a narrow cognitive task and deterministic code handles bookkeeping (citation resolution, validation, registry, confidence scoring). Citations 100% verbatim by construction. Same v4-compatible output schema + new `confidence` field per task.

**Architecture:** 13 stages, mostly mechanical with 4 LLM calls (Stages 2, 3, 5, 7 [per topic]). Backend is a stateless pipeline runner persisting state in `calls.call_topics_v5_*` columns. Stage 11 is a DB state, not a background wait — frontend detects awaiting_review and surfaces the banner.

**Reference spec:** `docs/project/config/calltopicsreview.md` (PRD with full per-stage specifications + locked decisions)

**Gold set:** `docs/project/config/gold set/` already contains v0.1 (3 transcripts + structured ground truth + evaluation criteria). See `gold_set_v0.1.json` for shape.

**Tech stack:** Python (backend services), TypeScript/React (frontend), Supabase Postgres. New table `topic_registry`. New JSONB columns on `calls`. DeepSeek v3.2 for dev/test; Opus 4.7 for production once gold-set-validated.

---

## File Structure

**Backend — new modules:**
- `backend/services/call_topics_v5/__init__.py` — package root, exports `run_pipeline(call_id)`
- `backend/services/call_topics_v5/stage_0_ingest.py` — line numbering, normalization
- `backend/services/call_topics_v5/stage_1_context.py` — project metadata + registry loader
- `backend/services/call_topics_v5/stage_2_atomic.py` — LLM atomic unit extraction
- `backend/services/call_topics_v5/stage_3_recall.py` — LLM adversarial recall pass
- `backend/services/call_topics_v5/stage_4_citations.py` — deterministic citation resolution
- `backend/services/call_topics_v5/stage_5_cluster.py` — LLM topic clustering with registry
- `backend/services/call_topics_v5/stage_6_reconcile.py` — registry reconciliation + new topic queue
- `backend/services/call_topics_v5/stage_7_synthesis.py` — per-topic LLM task synthesis
- `backend/services/call_topics_v5/stage_8_citations.py` — task-level citation attachment
- `backend/services/call_topics_v5/stage_9_confidence.py` — heuristic confidence scoring
- `backend/services/call_topics_v5/stage_10_validation.py` — hard + soft + clean validation
- `backend/services/call_topics_v5/stage_12_serialize.py` — v4-compatible JSON output
- `backend/services/call_topics_v5/orchestrator.py` — runs Stages 0-10, persists state, surfaces awaiting_review
- `backend/prompts/call_topics_v5_atomic.py` — Stage 2 prompt
- `backend/prompts/call_topics_v5_recall.py` — Stage 3 prompt
- `backend/prompts/call_topics_v5_cluster.py` — Stage 5 prompt
- `backend/prompts/call_topics_v5_synthesis.py` — Stage 7 prompt (per-topic)

**Backend — modified:**
- `backend/database/migrations/033_call_topics_v5_pipeline.sql` — DB schema
- `backend/routers/topics.py` — new endpoints: trigger pipeline, resolve review
- `backend/routers/calls.py` — endpoints already exist for cache PATCH

**Backend — tests:**
- `backend/tests/call_topics_v5/test_stage_0_ingest.py`
- `backend/tests/call_topics_v5/test_stage_1_context.py`
- `backend/tests/call_topics_v5/test_stage_2_atomic.py` (mock LLM)
- `backend/tests/call_topics_v5/test_stage_3_recall.py` (mock LLM)
- `backend/tests/call_topics_v5/test_stage_4_citations.py`
- `backend/tests/call_topics_v5/test_stage_5_cluster.py` (mock LLM)
- `backend/tests/call_topics_v5/test_stage_6_reconcile.py`
- `backend/tests/call_topics_v5/test_stage_7_synthesis.py` (mock LLM)
- `backend/tests/call_topics_v5/test_stage_8_citations.py`
- `backend/tests/call_topics_v5/test_stage_9_confidence.py`
- `backend/tests/call_topics_v5/test_stage_10_validation.py`
- `backend/tests/call_topics_v5/test_stage_12_serialize.py`
- `backend/tests/call_topics_v5/test_orchestrator.py` (end-to-end with mock LLMs)
- `backend/evaluation/` — gold set fixtures (symlink or copy) + eval harness (Stage 13)
  - Gold set source of truth: `docs/project/config/gold set/` (3 transcripts + `gold_set_v0.1.json`)
  - `evaluate.py` — runs pipeline against gold set + computes metrics
  - `metrics.py` — recall, precision, citation validity, naming stability, no_hallucination

**Frontend — new/modified:**
- `frontend/src/components/CallTopicsStage.tsx` — extend with Stage 11 banner (awaiting_review)
- `frontend/src/components/CallTopicsReviewBanner.tsx` (new) — review UI with 3 sections
- `frontend/src/components/PipelineProgressLog.tsx` (new) — replaces/extends ExtractionProgressLog with 13-stage trace
- `frontend/src/api/client.ts` — new endpoints: triggerV5, resolveReview
- `frontend/src/types/index.ts` — new types for V5 stages

---

## Database Schema (Migration 033)

```sql
-- Per-project canonical topic registry
CREATE TABLE topic_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  approved_by_call_id UUID REFERENCES calls(id),
  UNIQUE (project_id, lower(name))  -- case-insensitive unique per project
);
CREATE INDEX idx_topic_registry_project ON topic_registry(project_id);

-- Pipeline state + payload on calls
ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS call_topics_v5_state TEXT DEFAULT 'idle'
    CHECK (call_topics_v5_state IN ('idle', 'running', 'awaiting_review', 'done', 'failed')),
  ADD COLUMN IF NOT EXISTS call_topics_v5_payload JSONB DEFAULT NULL;

-- Payload shape (documented, not enforced):
-- {
--   "stages": { "0": {...}, "2": {atomic_units: [...]}, "5": {clusters: [...]}, ... },
--   "review_payload": {
--     "approvals_needed": [{type: "new_topic", proposal: {...}, suggested_match: ?}],
--     "confidence_review": [{task_id, confidence, snippet}],
--     "warnings": [{type, severity, location, message}]
--   },
--   "started_at": "...", "completed_at": "...", "model_used": "...", "params": {...}
-- }
```

---

## Build Order

5 phases. Each phase is independently testable against the gold set before the next is built.

1. **Foundation** — Stages 0, 1, 13 + DB migration
2. **Recall layer** — Stages 2, 3, 4
3. **Organization layer** — Stages 5, 6
4. **Synthesis layer** — Stages 7, 8
5. **Operational layer** — Stages 9, 10, 11, 12 + orchestrator wiring

---

## Phase 1 — Foundation

### Task 1.1 — DB schema (Migration 033)

**Files:**
- Create: `backend/database/migrations/033_call_topics_v5_pipeline.sql`

- [ ] Write the migration SQL per the schema section above.
- [ ] User applies it manually in Supabase (we don't auto-run migrations).
- [ ] Verify via curl: `GET /api/calls/{any_id}` returns `call_topics_v5_state` field.

**Acceptance:** new columns + table exist. Existing rows have `state = 'idle'`.

**Commit:** `[EPIC-17] DB: migration 033 — call_topics_v5_pipeline (topic_registry table + calls.call_topics_v5_state/_payload)`

---

### Task 1.2 — Stage 0 (transcript ingestion)

**Files:**
- Create: `backend/services/call_topics_v5/__init__.py`
- Create: `backend/services/call_topics_v5/stage_0_ingest.py`
- Create: `backend/tests/call_topics_v5/test_stage_0_ingest.py`

- [ ] Gold set transcripts ARE ALREADY numbered in `[NNNN] text` format (see `docs/project/config/gold set/arm_kickoff_05112026_numbered.txt`). Stage 0 must PARSE this format, not re-number.
- [ ] `ingest_transcript(raw: str) -> dict` returns `{lines: [{idx: "0001", text: "..."}], line_count: N}`.
  - Parse `[NNNN] <text>` line by line via regex `^\[(\d{4})\] (.*)$`.
  - If a line doesn't match the pattern, log warning + assign sequential idx as fallback (for legacy un-numbered transcripts not yet converted).
- [ ] For raw transcripts (no `[NNNN]` prefix): assign sequential 4-digit zero-padded idx as fallback path.
- [ ] Stable line indices: ingesting the same raw text twice → identical output.
- [ ] No silent drops — every non-empty line preserved (even if pattern match fails).
- [ ] Unit tests:
  - Pre-numbered transcript: parses correctly, idx stable
  - Raw transcript: fallback numbering works
  - Mixed (some pre-numbered, some not): pre-numbered preserved, others get fallback indices that don't collide
  - Empty input handled

**Acceptance:** All 3 gold set transcripts ingest cleanly, idx values are stable and match the `[NNNN]` prefixes in the source file.

**Commit:** `[EPIC-17] feat: Stage 0 — transcript ingestion (parses [NNNN] format + sequential fallback)`

---

### Task 1.3 — Stage 1 (project context + topic registry loader)

**Files:**
- Create: `backend/services/call_topics_v5/stage_1_context.py`
- Create: `backend/tests/call_topics_v5/test_stage_1_context.py`

- [ ] `load_context(project_id) -> dict` returns `{project_metadata: {name, description, ...}, topic_registry: [{id, name, description, approved_at}]}`.
- [ ] Empty registry returns `[]`, not error.
- [ ] Project-scoped — never returns registry entries from other projects.
- [ ] Unit tests: empty registry path, populated registry, project-not-found error.

**Acceptance:** Returns properly scoped context bundle.

**Commit:** `[EPIC-17] feat: Stage 1 — project context + topic registry loader`

---

### Task 1.4 — Gold set bootstrap (Stage 13 layer 1) — ALREADY DELIVERED

**Files (already in repo, no creation needed):**
- `docs/project/config/gold set/arm_kickoff_05112026_numbered.txt` (SWIB/ARM kickoff, 241 lines, 5 speakers, vocab high, registry empty)
- `docs/project/config/gold set/snowflake_kickoff_numbered.txt` (SWIB/Snowflake kickoff + scope debate, 278 lines, 6 speakers, registry partial)
- `docs/project/config/gold set/factset_05182026_numbered.txt` (SWIB/FactSet weekly umbrella, 297 lines, 5 speakers, registry populated)
- `docs/project/config/gold set/gold_set_v0.1.json` (structured ground truth + evaluation criteria + growth plan)
- `docs/project/config/gold set/call_topics_extraction_prd.md` (copy of PRD)

**No additional work for this task** — the user has already delivered the layer 1 gold set covering 3 distinct registry states (empty / partial / populated). Continue to Task 1.5.

**Layer 2 expansion** (deferred to later, per the growth plan in `gold_set_v0.1.json`):
- After Stage 6 ships: add `Boulevard_Charles_Livon` NWM session (tangent-heavy, NWM vocab)
- After Stage 8 ships: add 2nd FactSet umbrella sync (cross-call naming stability test)

**Acceptance:** all 3 transcripts + `gold_set_v0.1.json` are version-controlled and ready to be consumed by the evaluation harness.

**Commit:** N/A (gold set already in repo)

---

### Task 1.5 — Evaluation harness (Stage 13)

**Files:**
- Create: `backend/evaluation/__init__.py`
- Create: `backend/evaluation/evaluate.py`
- Create: `backend/evaluation/metrics.py`
- Create: `backend/evaluation/gold_set_loader.py`

- [ ] `gold_set_loader.py`: reads `docs/project/config/gold set/gold_set_v0.1.json` + the 3 numbered transcript files. Returns iterable of `{transcript_id, raw_text, ground_truth}` per entry.
- [ ] `evaluate.py` CLI: `python -m backend.evaluation.evaluate --gold-set v0.1 --output report.json [--transcript-id arm_kickoff_05112026]`
- [ ] Pipeline integration: calls `run_pipeline(transcript)` if it exists, else uses placeholder (Phase 1 → eval still runs, just reports "pipeline not yet built").
- [ ] `metrics.py` — implements ALL evaluation criteria from `gold_set_v0.1.json::evaluation_criteria`:
  - **`topic_recall`** (primary, target ≥0.95): `|extracted ∩ expected| / |expected|`. Topic match = canonical name OR close semantic match (fuzzy, e.g. token Jaccard ≥0.6).
  - **`topic_precision`** (secondary, target ≥0.85): `|extracted ∩ expected| / |extracted|`. Topics in `topics_explicitly_excluded` that appear count as false positives.
  - **`task_recall`** (secondary, target ≥0.80): for each correctly-matched topic, fraction of `expected_tasks` whose `must_have_keywords` all appear in pipeline-output tasks.
  - **`citation_validity`** (must-pass, target =1.00): fraction of pipeline-output citations that match transcript text byte-for-byte. Use the same verbatim check as Pass ① currently.
  - **`citation_coverage`** (secondary, target ≥0.90): for each correctly-matched topic, citations overlap the `evidence_line_ranges` (any overlap counts).
  - **`naming_stability`** (must-pass, target =1.00): run pipeline 5× on same transcript, all runs produce identical topic name sets.
  - **`no_hallucination`** (must-pass, target =0): no topic in `topics_explicitly_excluded` appears in pipeline output. Match by name (canonical or close semantic).
- [ ] Per-metric pass/fail flag based on the target. Output report includes per-transcript breakdown + overall summary.
- [ ] Stage-by-stage skip: if a stage isn't built yet, evaluate skips dependent metrics (e.g. naming_stability requires Stages 0-12; just runs what's available + reports "N/A — Stage X not yet built").
- [ ] CLI output: pretty colored table + JSON report. Exit code non-zero if any must-pass metric fails.
- [ ] Runs in < 5 minutes for all 3 transcripts × 5 re-runs (for stability metric).
- [ ] Unit tests for each metric function (with synthetic input).

**Acceptance:** Runs against all 3 gold transcripts, produces pass/fail per metric, must-pass failures exit non-zero. Topology-stable naming run.

**Commit:** `[EPIC-17] eval: Stage 13 — full evaluation harness (7 metrics, 3 must-pass, per-transcript breakdown)`

---

## Phase 2 — Recall Layer

### Task 2.1 — Stage 2 (atomic unit extraction)

**Files:**
- Create: `backend/prompts/call_topics_v5_atomic.py`
- Create: `backend/services/call_topics_v5/stage_2_atomic.py`
- Create: `backend/tests/call_topics_v5/test_stage_2_atomic.py`

- [ ] Prompt body (`CALL_TOPICS_V5_ATOMIC_PROMPT`): "Extract every meaningful atomic unit (task, decision, question, blocker, statement). Do not group. Do not deduplicate. Optimize for recall. Each unit anchored to `[start_line, end_line]` from the numbered transcript."
- [ ] `extract_atomic_units(numbered_transcript, context_bundle, *, llm, model) -> list[dict]` — returns list of `{unit_id, type, text, owner, evidence_lines: [start, end]}`. unit_id is `u_NNNN` sequential, deterministic per run.
- [ ] Temperature 0 hardcoded.
- [ ] Schema validation: every unit has type ∈ {task, decision, question, blocker, statement}, evidence_lines within transcript bounds.
- [ ] Unit tests with mock LLM: schema enforcement, invalid line ranges rejected, unit_id sequencing.

**Acceptance:** Output is a flat list of valid atomic units. Each unit has a valid line range. Temperature is 0 (logged).

**Commit:** `[EPIC-17] feat: Stage 2 — atomic unit extraction (LLM call, temperature 0)`

---

### Task 2.2 — Stage 3 (adversarial recall pass)

**Files:**
- Create: `backend/prompts/call_topics_v5_recall.py`
- Create: `backend/services/call_topics_v5/stage_3_recall.py`
- Create: `backend/tests/call_topics_v5/test_stage_3_recall.py`

- [ ] Prompt: "Here is the full numbered transcript. Here are N atomic units already extracted. **What did we miss?** Return only NEW units. Empty list if nothing missed."
- [ ] `recall_pass(numbered_transcript, existing_units, *, llm, model) -> list[dict]` — same shape as Stage 2 output. New `unit_id`s continue the sequence.
- [ ] Runs unconditionally (no skip).
- [ ] Merge: `merged_pool = stage_2_units + stage_3_units`. Validate no duplicate `unit_id`s.
- [ ] Unit tests with mock LLM: empty additions handled, duplicate detection, sequence continuity.

**Acceptance:** Gold-set evaluation shows recall improvement vs Stage 2 alone (compare on transcript_01_swib).

**Commit:** `[EPIC-17] feat: Stage 3 — adversarial recall pass + merged unit pool`

---

### Task 2.3 — Stage 4 (citation resolution)

**Files:**
- Create: `backend/services/call_topics_v5/stage_4_citations.py`
- Create: `backend/tests/call_topics_v5/test_stage_4_citations.py`

- [ ] **NO LLM call.** Pure code.
- [ ] `resolve_citations(units, numbered_transcript) -> list[dict]` — for each unit, resolve `evidence_lines: [start, end]` to actual transcript text (join lines with `\n`). Attach as `citation` field.
- [ ] Validation: line ranges within bounds, resolved citation non-empty. Failing units flagged (not dropped) — `unit["citation_valid"] = False, unit["validation_error"] = "..."` for Stage 10 to handle.
- [ ] Unit tests: byte-for-byte identity, out-of-bounds handling, multi-line citations.

**Acceptance:** 100% of `citation` fields are byte-identical to the corresponding transcript text. No LLM call in this stage.

**Commit:** `[EPIC-17] feat: Stage 4 — deterministic citation resolution from line refs`

---

## Phase 3 — Organization Layer

### Task 3.1 — Stage 5 (topic clustering)

**Files:**
- Create: `backend/prompts/call_topics_v5_cluster.py`
- Create: `backend/services/call_topics_v5/stage_5_cluster.py`
- Create: `backend/tests/call_topics_v5/test_stage_5_cluster.py`

- [ ] Prompt: "Group the following atomic units into topics. Prefer registry names (provided below). Only propose new names if nothing in the registry matches. Each unit_id appears in EXACTLY one topic."
- [ ] `cluster_topics(atomic_units, topic_registry, *, llm, model) -> list[dict]` — returns `[{topic_name, unit_ids: [...], new_topic: bool, importance: low|medium|high}]`.
- [ ] Schema validation: every `unit_id` from the pool appears in exactly one topic (no orphans, no duplicates).
- [ ] Topics matched to registry use the canonical name (exact string match).
- [ ] New topic proposals flagged `new_topic: true`.
- [ ] Unit tests with mock LLM: orphan detection, duplicate detection, registry-name preference.

**Acceptance:** Every atomic unit appears in exactly one topic. Registry-matched topics use canonical name.

**Commit:** `[EPIC-17] feat: Stage 5 — topic clustering with registry as preferred vocabulary`

---

### Task 3.2 — Stage 6 (registry reconciliation)

**Files:**
- Create: `backend/services/call_topics_v5/stage_6_reconcile.py`
- Create: `backend/tests/call_topics_v5/test_stage_6_reconcile.py`

- [ ] **NO LLM call.** Pure code.
- [ ] `reconcile_with_registry(clusters, topic_registry) -> dict` — returns:
  ```python
  {
    "working_topics": [
      {"topic_name": "...", "unit_ids": [...], "registry_id": uuid_or_null, "provisional": bool}
    ],
    "new_topic_proposals": [
      {"proposed_name": "...", "unit_ids": [...], "suggested_match_id": uuid_or_null, "lexical_similarity_to_existing": 0.0-1.0}
    ]
  }
  ```
- [ ] Working topics keep canonical names for matched, provisional for new.
- [ ] For each new proposal, lexical-match against registry (Jaccard on tokens) — if similarity ≥ 0.6, flag `suggested_match_id` so Stage 11 can offer "merge with existing".
- [ ] No automatic registry mutation.
- [ ] Unit tests: matched + new + suggested-match-detection paths.

**Acceptance:** Working topics list ready for downstream. New topic proposals queued with similarity hints.

**Commit:** `[EPIC-17] feat: Stage 6 — registry reconciliation + new topic queue with similarity hints`

---

## Phase 4 — Synthesis Layer

### Task 4.1 — Stage 7 (per-topic task synthesis)

**Files:**
- Create: `backend/prompts/call_topics_v5_synthesis.py`
- Create: `backend/services/call_topics_v5/stage_7_synthesis.py`
- Create: `backend/tests/call_topics_v5/test_stage_7_synthesis.py`

- [ ] Prompt: "Here are atomic units assigned to topic X with their citations. Synthesize them into structured tasks. Each task: `{task, next_step, owner, status, key_terms, open_questions, decisions, evidence_unit_ids: [...]}`. Every task must reference ≥2 evidence unit_ids."
- [ ] `synthesize_topic(topic, *, llm, model) -> dict` — returns `{topic_name, tasks: [...]}`. Per-topic call (narrow context).
- [ ] Schema validation: tasks have all required fields, evidence_unit_ids each ≥ 2 and present in the topic's unit_ids.
- [ ] **Sequential baseline** — Stage 7 calls run sequentially per topic. Parallelization deferred.
- [ ] Unit tests with mock LLM: per-topic isolation, schema enforcement, evidence linkage.

**Acceptance:** Each topic's tasks reference ≥2 evidence units from THAT topic's unit pool. Per-topic context window.

**Commit:** `[EPIC-17] feat: Stage 7 — per-topic task synthesis (sequential, per-topic LLM call)`

---

### Task 4.2 — Stage 8 (task-level citation attachment)

**Files:**
- Create: `backend/services/call_topics_v5/stage_8_citations.py`
- Create: `backend/tests/call_topics_v5/test_stage_8_citations.py`

- [ ] **NO LLM call.** Pure code.
- [ ] `attach_citations(tasks, atomic_unit_pool) -> list[dict]` — for each task, walk `evidence_unit_ids`, collect citations from units, attach to `task.citations` list. Enforce ≥2.
- [ ] Tasks with < 2 citations are flagged (not dropped) for Stage 10.
- [ ] Unit tests: byte-identity of citations, count enforcement, flag on shortage.

**Acceptance:** Task citations are byte-identical to source atomic unit citations. Tasks below ≥2 flagged.

**Commit:** `[EPIC-17] feat: Stage 8 — deterministic task-level citation attachment`

---

## Phase 5 — Operational Layer

### Task 5.1 — Stage 9 (confidence scoring)

**Files:**
- Create: `backend/services/call_topics_v5/stage_9_confidence.py`
- Create: `backend/tests/call_topics_v5/test_stage_9_confidence.py`

- [ ] **NO LLM call.** Pure heuristic code.
- [ ] `compute_confidence(task, all_units, topic, registry_match) -> dict` — returns `{score: 0.0-1.0, signals: {atomic_units: N, distinct_speakers: M, owner_clarity: bool, citation_count: K, registry_topic: bool}}`.
- [ ] Initial weights (will be tuned against gold set):
  - `atomic_units` (count of supporting units, capped at 5): weight 0.30
  - `distinct_speakers` (count): weight 0.20
  - `owner_clarity` (explicit non-empty owner): weight 0.15
  - `citation_count` (capped at 4): weight 0.20
  - `registry_topic` (matched vs new): weight 0.15
- [ ] Each signal contributes a 0.0-1.0 score; weighted sum is the final.
- [ ] Score deterministic given same inputs.
- [ ] Unit tests: each signal in isolation, weighted combinations, edge cases (empty owner, single citation).

**Acceptance:** Score correlates with ground-truth importance on gold set (Pearson r ≥ 0.5 initial target, ≥ 0.7 after tuning).

**Commit:** `[EPIC-17] feat: Stage 9 — heuristic confidence scoring (5 signals, configurable weights)`

---

### Task 5.2 — Stage 10 (validation, 3 categories)

**Files:**
- Create: `backend/services/call_topics_v5/stage_10_validation.py`
- Create: `backend/tests/call_topics_v5/test_stage_10_validation.py`

- [ ] **NO LLM call.** Pure code.
- [ ] Three categories per PRD:
  - **Hard failures (blocking)**:
    - Schema violations
    - Off-transcript citations (line range out of bounds, quote not byte-identical)
    - Orphan units (not assigned to any topic in Stage 5)
    - Missing required fields
    - Tasks with <2 verbatim-verified citations
    - Topic with 0 tasks
    - Duplicate topic names within run
    - Owner non-empty-or-`unassigned`
    - **NEW** Pipeline output contains a topic name matching ANY entry in the active project's `topics_explicitly_excluded` list (anti-hallucination — sourced from gold set or per-project blacklist). Note: this is a runtime safeguard, not just a gold-set metric.
  - **Soft failures (warnings, non-blocking)**:
    - Task with ≥2 citations from same speaker, lines within 5 of each other (weak evidence)
    - Topic with exactly 1 task at confidence 0.45-0.55 (boundary zone)
    - Topic where 80%+ of unit lines fall within a 30-line window (narrow basis)
    - New topic proposal with lexical similarity ≥ 0.6 to existing registry entry (possible duplicate)
    - **NEW** New topic proposal lexically similar (≥0.5 Jaccard) to ANY entry in `topics_explicitly_excluded` for that project (suggests user's intent was to NOT track this — flag for review)
  - **Clean**: passes all hard + no warnings + no new topics + no low-confidence tasks → Stage 11 skipped.
- [ ] `validate(extraction) -> dict` returns `{hard_failures: [...], soft_warnings: [...], clean: bool}`.
- [ ] Hard failure response: retry the originating stage once; if still fails, escalate to Stage 11 as `approvals_needed` entry.
- [ ] Soft warning thresholds documented as constants — tunable.
- [ ] Unit tests for each hard rule + each soft warning rule.

**Acceptance:** All hard rules deterministic. Soft warnings produce 0-2 entries on the gold transcript (post-tuning). Clean runs detected correctly.

**Commit:** `[EPIC-17] feat: Stage 10 — 3-category validation (hard / soft / clean) + retry policy`

---

### Task 5.3 — Stage 12 (final output serialization)

**Files:**
- Create: `backend/services/call_topics_v5/stage_12_serialize.py`
- Create: `backend/tests/call_topics_v5/test_stage_12_serialize.py`

- [ ] **NO LLM call.** Pure code.
- [ ] `serialize_to_v4(approved_extraction, registry_updates) -> list[dict]` — outputs v4-compatible JSON (topics with per-task `task, next_step, owner, status, key_terms, open_questions, decisions, citations, confidence`).
- [ ] On call: writes to `calls.extraction_cache` + sets state to `done` + applies approved registry updates to `topic_registry` table.
- [ ] Unit tests: v4 schema compatibility, registry write atomicity (transactional).

**Acceptance:** Output matches v4 schema exactly. `confidence` field present per task. Registry write happens only on serialization success.

**Commit:** `[EPIC-17] feat: Stage 12 — v4-compatible serialization + atomic registry update`

---

### Task 5.4 — Orchestrator (pipeline runner)

**Files:**
- Create: `backend/services/call_topics_v5/orchestrator.py`
- Create: `backend/tests/call_topics_v5/test_orchestrator.py`

- [ ] `run_pipeline(call_id) -> None` — runs Stages 0-10 sequentially. Persists per-stage output to `calls.call_topics_v5_payload.stages[i]`.
- [ ] Per-stage progress logged via existing `ProgressLogger` pattern (`calls.extract_call_progress`). Format: `Stage N: <short description>… <metric>`.
- [ ] After Stage 10:
  - If clean + no new topics + no low-confidence → run Stage 12 immediately. State → `done`.
  - Otherwise → State → `awaiting_review`. Payload includes review_payload with 3 sections (approvals_needed, confidence_review, warnings). User must resolve via dedicated endpoint.
- [ ] Hard failure handling: retry the affected stage once, then escalate as approval.
- [ ] State transitions: idle → running → (done | awaiting_review | failed). On crash, state → failed (visible to user).
- [ ] Unit tests with mocked stages: happy path, awaiting_review path, retry path, failure path.

**Acceptance:** Full pipeline runs end-to-end against gold set with all mocked LLM calls. State machine correctly transitions.

**Commit:** `[EPIC-17] feat: orchestrator — runs Stages 0-10 + state machine + progress logging`

---

### Task 5.5 — Stage 11 backend endpoints

**Files:**
- Modify: `backend/routers/topics.py` (or new `backend/routers/call_topics_v5.py`)

- [ ] `POST /api/calls/{call_id}/call-topics-v5/run` — triggers `run_pipeline(call_id)` via BackgroundTasks. Returns 202 + state info.
- [ ] `GET /api/calls/{call_id}/call-topics-v5/state` — returns `{state, payload}`. Frontend polls.
- [ ] `POST /api/calls/{call_id}/call-topics-v5/resolve-review` — body: `{approved_new_topics: [{proposed_name, registry_action: "approve" | "merge" | "reject", merge_with_id?}], confidence_decisions: [{task_id, action: "approve" | "edit" | "drop", edits?}], acknowledged_warnings: [warning_id]}`. On success: applies all decisions, advances to Stage 12, state → `done`.
- [ ] Unit tests: each endpoint, validation of payload shapes, idempotency.

**Acceptance:** Endpoints work end-to-end. State machine respected (can't resolve-review on a running pipeline).

**Commit:** `[EPIC-17] feat: backend endpoints — trigger v5 pipeline, poll state, resolve review`

---

### Task 5.6 — Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] Types: `CallTopicsV5State`, `CallTopicsV5Payload`, `ReviewPayload`, `ApprovalNeeded`, `ConfidenceReviewItem`, `Warning`.
- [ ] API methods: `callTopicsV5.run(callId)`, `callTopicsV5.getState(callId)`, `callTopicsV5.resolveReview(callId, decisions)`.
- [ ] Extend `Call` interface with `call_topics_v5_state`, `call_topics_v5_payload`.

**Commit:** `[EPIC-17] feat(fe): v5 pipeline types + API client`

---

### Task 5.7 — Stage 11 frontend banner + PipelineProgressLog

**Files:**
- Create: `frontend/src/components/CallTopicsReviewBanner.tsx`
- Create: `frontend/src/components/PipelineProgressLog.tsx`
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] `PipelineProgressLog` renders 13-stage trace from `extract_call_progress.__progress__`. Status icons per stage (running spinner / done check / failed cross). Stage 11 status (awaiting_review / skipped / done) clearly shown.
- [ ] `CallTopicsReviewBanner` shows when `call.call_topics_v5_state === "awaiting_review"`. 3 sections:
  - **Approvals needed** (red): new topic proposals + hard escalations. Each entry: name + suggested match (if any) + Approve/Merge/Reject buttons.
  - **Confidence review** (amber): low-confidence tasks. Each entry: task text + confidence badge + Approve/Edit/Drop buttons.
  - **Warnings** (yellow): each entry: type + message + Acknowledge button.
- [ ] CallTopicsStage extended to render the banner at top when state is `awaiting_review`. Existing extraction trigger now calls v5 endpoint when feature-flagged on (see Task 5.10).
- [ ] After all sections resolved → button "Apply & Continue" → triggers `resolveReview` → state → `done` → topics appear in the existing table view (rendered from `extraction_cache` post-Stage 12).
- [ ] Unit tests / smoke tests on the banner state machine.

**Acceptance:** User can run pipeline, see all 13 stages in log, resolve review when awaiting_review, see final topics in existing UI.

**Commit:** `[EPIC-17] feat(fe): Stage 11 banner + 13-stage pipeline progress log`

---

### Task 5.8 — Soft warning threshold tuning

**Files:**
- Modify: `backend/services/call_topics_v5/stage_10_validation.py`
- Modify: `backend/evaluation/evaluate.py`

- [ ] Add a `tune_thresholds.py` script that runs against the gold set and tries different threshold values for each soft warning rule.
- [ ] Output: recommended threshold per rule + acknowledgment rate prediction.
- [ ] Document final thresholds in the source with a comment block.
- [ ] Add warning-rate metric to the eval harness output.

**Acceptance:** Clean gold-set transcript produces 0-2 warnings. Documented threshold choices.

**Commit:** `[EPIC-17] eval: soft warning threshold tuning script + final thresholds documented`

---

### Task 5.9 — Confidence weight tuning

**Files:**
- Modify: `backend/services/call_topics_v5/stage_9_confidence.py`
- Modify: `backend/evaluation/evaluate.py`

- [ ] Add `tune_confidence_weights.py` that grid-searches weights against gold set's expected importance ranking.
- [ ] Output: recommended weights + Pearson correlation.
- [ ] Document final weights with a comment block.

**Acceptance:** Confidence scores on gold transcript correlate with ground-truth importance at r ≥ 0.7.

**Commit:** `[EPIC-17] eval: confidence weight tuning + final weights documented (r ≥ 0.7 on gold set)`

---

### Task 5.10 — Feature flag + cutover

**Files:**
- Modify: `backend/services/topics_service.py::run_extraction_background`
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] Feature flag `CALL_TOPICS_V5_ENABLED` (env var or `system_settings` column). Default OFF.
- [ ] When ON, `run_extraction_background` delegates to v5 orchestrator. When OFF, v4 single-shot path runs as before (unchanged).
- [ ] Frontend reads feature flag from `/api/settings`, conditionally enables the new banner + progress log.
- [ ] Document the flag in `workflow/ADR.md` (architectural decision).

**Acceptance:** Flag off → v4 behavior unchanged. Flag on → v5 pipeline runs. Per-project enable possible (future).

**Commit:** `[EPIC-17] feat: feature flag CALL_TOPICS_V5_ENABLED + soft cutover (v4 default off)`

---

## Cross-cutting Tasks (run alongside phases)

### Task X.1 — Logging & observability

**Files:**
- Modify: each Stage module

- [ ] Every LLM call logs: stage name, model, temperature, token counts (input + output), latency_ms, retry count.
- [ ] Every stage logs: input size, output size, validation outcome.
- [ ] Logs aggregated in `extract_call_progress` (visible to user) + standard backend log (engineering audit).

**Acceptance:** Any single run can be reconstructed from logs.

---

### Task X.2 — Retry & error policy

**Files:**
- Create: `backend/services/call_topics_v5/retry.py`

- [ ] Centralised retry helper: `with_retry(fn, max_attempts=2, on_failure=...)`. Used in LLM stages.
- [ ] Hard validation failures → retry the originating stage once → escalate as approval.
- [ ] LLM API errors (rate limit, timeout) → exponential backoff, max 3 attempts.

**Acceptance:** Single retry on validation failure. LLM API failures handled with backoff.

---

### Task X.3 — Registry persistence + admin

**Files:**
- Modify: `backend/routers/projects.py` (or new `backend/routers/topic_registry.py`)

- [ ] `GET /api/projects/{project_id}/topic-registry` — list entries
- [ ] `PATCH /api/projects/{project_id}/topic-registry/{id}` — rename or update description
- [ ] `DELETE /api/projects/{project_id}/topic-registry/{id}` — remove (cascades? warning if referenced)
- [ ] No `POST` — registry entries are created only via Stage 11 approval.

**Acceptance:** Registry inspectable + editable post-creation. New entries gated through Stage 11.

---

## Open Decisions (track + resolve during build)

- **Confidence threshold for Stage 11 review**: initial 0.5; tune against gold set in Task 5.9.
- **Retry policy specifics**: single retry on hard validation failure (locked). LLM API errors: 3 attempts with backoff (locked).
- **Stage 7 parallelism**: sequential baseline (locked). Parallelize via `asyncio.gather` deferred to a follow-up if latency > 60s on real calls.
- **Lexical similarity threshold for new-topic-merge-suggestion**: initial Jaccard 0.6 (Task 3.2). Tune against gold set.
- **Hard failure escalation UI**: surface as approval entries with "Auto-retry succeeded" or "Manual fix needed" labels. Detailed UX in Task 5.7.
- **Per-project `topics_explicitly_excluded` storage**: gold set's notion of "excluded topics" needs a per-project equivalent in production. Two paths:
  - (A) New DB table `project_topic_exclusions(project_id, topic_name, reason, added_at)` — populated by user via admin UI.
  - (B) Pipeline derives exclusions from past-call rollbacks / user-rejected new topic proposals in Stage 11.
  Recommend (A) for explicit control. Decide in Phase 5.

---

## Self-review

- ✅ All 13 stages have an explicit task with files, behavior, acceptance criteria.
- ✅ DB migration defined with schema + soft-cutover compatible.
- ✅ Gold set is layer-1 bootstrap (1 transcript) per locked decision.
- ✅ Model is DeepSeek for dev/test (configurable per call), Opus 4.7 once gold-set-validated.
- ✅ Stage 11 architecture is state-machine (no backend wait) per locked decision.
- ✅ 3-category validation (hard / soft / clean) integrated into Stage 10 + Stage 11 sections.
- ✅ Feature flag + soft cutover for migration of existing projects.
- ✅ Cross-cutting (logging, retry, registry admin) scoped as separate tasks.
- ⚠️ Risk: gold set creation is on the critical path. If user delivers transcripts late, Phase 1 blocks. Mitigation: build Phase 1 code skeletons in parallel; eval harness can run with placeholder ground truth initially.
- ⚠️ Risk: Opus 4.7 token costs unknown until gold-set validation. Mitigation: tracking token usage per stage from day one (Task X.1).

## Execution Handoff

Recommended cadence per phase:
- **Phase 1** complete → run eval harness with placeholder pipeline (Stages 0-1 only) → confirm gold set ingestion + metrics framework works.
- **Phase 2** complete → eval harness reports atomic unit recall + citation validity ON GOLD SET. Decide if recall is sufficient before continuing.
- **Phase 3** complete → eval reports topic recall + naming stability across re-runs.
- **Phase 4** complete → eval reports full task extraction quality vs ground truth.
- **Phase 5** complete + Task 5.10 feature flag → enable on 1 test project. Compare v4 vs v5 on a real transcript. Decide on cutover.
