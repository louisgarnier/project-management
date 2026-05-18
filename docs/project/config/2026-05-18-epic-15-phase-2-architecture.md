# Architecture — EPIC-15 Phase 2: Artifacts Rebuild + xlsx Tracker

> **Source PRD:** `docs/project/config/2026-05-18-epic-15-phase-2-prd.md`
> **Source brainstorm:** `docs/project/config/2026-05-18-epic-15-phase-2-brainstorm.md` (GO)
> **Approved mockups:** `phase2-call-topics-extended.html`, `phase2-project-tracker-tab-v3.html`
> **Status:** `[x] Draft` → `[ ] Reviewed` → `[ ] Locked`

---

## 1. Tech Stack — deltas

**No new packages.** openpyxl is already in `requirements.txt` (used by EPIC-12 + earlier).

| Layer | Choice | Notes |
|---|---|---|
| Backend framework | FastAPI (existing) | New router endpoint for xlsx export |
| DB | Supabase Postgres (existing) | Single new migration `027_epic15_phase2_schema.sql` |
| Frontend | Next.js (existing) | New sub-tab + 5 sub-views inside Artifacts page |
| xlsx generator | **openpyxl** (already installed) | New module `backend/exporters/xlsx_tracker.py` |
| LLM | OpenRouter + deepseek/deepseek-v3.2 (Phase 1 default) | Two new LLM artifact types: chronology narrative + RAG verification |

---

## 2. Resolved Open Questions (from PRD §10)

| Q | Decision |
|---|---|
| **Q1 — `closed_in_call_id` re-flip** | **Latest.** Each time a task's status flips from non-resolved → resolved, overwrite `closed_in_call_id` with the current call's id. Captures "most-recently-decided" semantics. |
| **Q2 — Chronology cell length** | **Cap at 400 characters / 3 sentences max** in the LLM prompt. Hard truncation server-side at 600 chars if model misbehaves. |
| **Q3 — Default sub-view** | **Dashboard.** Sub-tab loads Dashboard on first render. URL hash `#dashboard` for shareability; other views `#chronology`, `#anchors`, `#decisions`, `#key-terms`. |
| **Q4 — Existing 4 LLM artifact prompts** | **Trust context engine.** Keep the 4 prompt bodies (Executive Summary, Email Summary, Email Follow-up, Next Call Agenda) unchanged. The new 4-value `context_scope` delivers new-shape data; smoke-test reveals if quality issues require a prompt rewrite later. |
| **Q5 — xlsx filename** | `<project_slug>-tracker-<ISO_date>.xlsx` — e.g. `factset-swib-tracker-2026-05-18.xlsx`. Slug = `_slugify(project.name)` already in `backend/services/export_service.py`. |
| **Q6 — `all_call_transcripts` scope** | **Include current call.** Most useful for "summarise across all calls so far" prompts. |

---

## 3. Schema (Migration 027)

`backend/database/migrations/027_epic15_phase2_schema.sql`

```sql
-- Migration 027 — EPIC-15 Phase 2: open_questions/decisions, chronology, context_scope enum
-- Run manually in Supabase Dashboard → SQL Editor.

SET search_path = public;

-- ── 1. topic_updates: new arrays + chronology fields ────────────────────
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS open_questions       JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS decisions            JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS chronology_narrative TEXT,
  ADD COLUMN IF NOT EXISTS rag_verification_note TEXT;

-- ── 2. artifact_library.context_scope CHECK update ──────────────────────
-- Old check was on string values "call" / "project". Migrate first, then constrain.

UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE context_scope = 'call';

UPDATE public.artifact_library
   SET context_scope = 'all_project_topics'
 WHERE context_scope = 'project';

ALTER TABLE public.artifact_library
  DROP CONSTRAINT IF EXISTS artifact_library_context_scope_check;
ALTER TABLE public.artifact_library
  ADD CONSTRAINT artifact_library_context_scope_check
  CHECK (context_scope IN (
    'this_call_transcript',
    'all_call_transcripts',
    'this_call_topics',
    'all_project_topics'
  ));

-- ── 3. Explicit per-artifact scope migration (overrides the bulk migration above) ──
-- Email Summary + Email Follow-up + Executive Summary + Next Call Agenda all use this_call_topics.
-- Risk Register is project-wide → all_project_topics. Decisions Digest is per-call.
UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE name IN ('Executive Summary', 'Email Summary (1-pager)',
                'Email Follow-up (pre-next-call)', 'Next Steps & Action Items',
                'Questions for Stakeholders', 'Decisions Digest');

UPDATE public.artifact_library
   SET context_scope = 'all_project_topics'
 WHERE name IN ('Risk Register', 'Next Call Agenda');

-- (Tier-1 workflow prompts call_topics / project_topics / merge_verification /
-- not_discussed_check are pipeline-internal — their context_scope is unused at
-- runtime. Set them to 'this_call_topics' to satisfy the CHECK constraint.)
UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE category IN ('call_topics', 'project_topics', 'merge_verification', 'not_discussed_check');

NOTIFY pgrst, 'reload schema';
```

**No new tables.** All Phase 2 data piggybacks on existing `topic_updates` and `artifact_library`.

### Per-item lifecycle metadata (lives inside JSONB elements)

Each element in `tasks[]` / `open_questions[]` / `decisions[]` carries:

```json
{
  "id": "uuid",                          // existing for tasks (task_id); new key id for open_questions + decisions
  "added_in_call_id": "uuid",            // NEW — set when first inserted
  "closed_in_call_id": "uuid | null",    // NEW — tasks + open_questions only; set when status flips → resolved (latest wins)
  ...domain fields (task/next_step/owner/status for tasks; text/owner/status for open_questions; text for decisions)...
}
```

Decisions are immutable post-commit — their `added_in_call_id` doubles as "decided_in" for the Decisions log sheet.

---

## 4. Component Breakdown

### 4.1 Backend

**`backend/prompts/call_topics.py`** — extend `CALL_TOPICS_V2_PROMPT_BODY` → v3
- Add two new sections to the rubric: `open_questions[]` and `decisions[]`.
- Preserve the DUAL-CLASSIFY rule (investigate/verify/check-style tasks also go to open_questions).
- Output JSON shape now has 6 top-level fields per topic: `name`, `importance`, `key_terms`, `evidence`, `tasks`, `open_questions`, `decisions`.

**`backend/services/topics_service.py`**
- Update `_TOPIC_SCHEMA` constant to describe the v3 output.
- Extend `_validate_topic` to require `open_questions` (list, may be empty) + `decisions` (list, may be empty). Validate inner items have required fields.
- Extend `_stamp_task_ids` → rename to `_stamp_item_ids` (or wrap): stamp UUIDs onto items in all 3 arrays, set `added_in_call_id` from the current call_id.
- New helper `_apply_lifecycle_on_resolve(prev_tasks, new_tasks, call_id)` — diffs status transitions and writes `closed_in_call_id` (latest wins per Q1).
- `_persist_topic_update` writes the 3 arrays + chronology fields. The new chronology fields default to NULL until the LLM artifact populates them.

**`backend/prompts/chronology.py`** — NEW
- `CHRONOLOGY_NARRATIVE_PROMPT_BODY` — instructs the LLM to write a 2-3 sentence summary of what happened to a given topic in a given call. Hard cap: 3 sentences / 400 chars.
- `CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY` — given a narrative + the underlying transcript snippet, returns either "verified" or a short drift note ("Apr 13 narrative claims X but transcript does not contain X").

**`backend/services/chronology_service.py`** — NEW
- `generate_chronology_cell(project_topic_id, call_id, db) -> (narrative, rag_note)`:
  1. Load the topic_update row for this (topic, call). If absent → skip.
  2. Resolve LLM provider/model from artifact_library row `Chronology Narrative` (system-default `seeded_by_default=true`).
  3. Call LLM #1 → narrative; truncate to 600 chars defensively.
  4. Call LLM #2 → RAG verification, given the narrative + the relevant transcript excerpt(s).
  5. Persist both to `topic_updates.chronology_narrative` + `rag_verification_note`.
  6. On failure: persist `narrative=""` + `rag_verification_note="(generation failed: <reason>)"` so the pipeline doesn't block (NFR-P2-03).

**`backend/library/seed.py`** — extend `SYSTEM_LIBRARY`
- Add 2 new system entries (both `kind=llm`, `seeded_by_default=true`):
  - `Chronology Narrative` (category=`call_topics` is reserved; create new category `chronology` if needed — or piggyback on existing categories. Recommend new category `chronology`.)
  - `RAG Verification`
- Both use `openrouter / deepseek/deepseek-v3.2`.
- Update `context_scope` on existing entries per migration §3 to ensure consistency on fresh installs.

**`backend/services/topic_updates_accumulator.py`** — NEW (or extend existing kanban_service)
- New function `accumulate_into_project_state(call_id, db)` triggered at `project_updates` stage commit:
  1. For each topic_update row for this call:
     - Append items to project-level rollups (the project view reads from `topic_updates` anyway — this function's responsibility is **stamping lifecycle metadata** and **triggering chronology generation**, not maintaining a duplicate project-level table).
     - Stamp `added_in_call_id` on any new items (already done at extraction; re-stamp defensively if missing).
     - Diff prior call's resolved status — stamp `closed_in_call_id` on items that flipped.
  2. Trigger `chronology_service.generate_chronology_cell(...)` for every topic touched in this call.

**`backend/services/artifact_generation.py` (or wherever `gen_one` lives)** — context-assembly seam
- New helper `_assemble_context(scope, call_id, project_id, db) -> str`:
  - `this_call_transcript` → return `calls.transcript` for `call_id`.
  - `all_call_transcripts` → concatenate every call's transcript in this project (chronological), labeled by call date.
  - `this_call_topics` → list_call_topics(call_id) rendered as structured text.
  - `all_project_topics` → list_project_topics(project_id) rendered as structured text including chronology cells.
- Wire `gen_one` to call `_assemble_context(artifact_type.context_scope, ...)` before invoking the LLM.

**`backend/exporters/xlsx_tracker.py`** — NEW
```python
# Module exports a single function:
def build_tracker_xlsx(project_id: str) -> bytes:
    """Render 5 sheets to a BytesIO via openpyxl and return the bytes."""
```
- Reads project topics + topic_updates via existing `list_project_topics` + `list_topics_timeline`.
- 5 sheets named exactly as v04: `Dashboard`, `Chronology`, `Anchors lifecycle`, `Decisions log`, `Key terms registry`.
- Each sheet header row matches v04 column order. Static styling: bold header row, frozen top row, column-widths tuned.
- No charts, no conditional formatting, no pivots (NG3).

**`backend/routers/projects.py`** (or existing)
- New endpoint: `GET /api/projects/{project_id}/export.xlsx`
- Calls `build_tracker_xlsx(project_id)`, returns `StreamingResponse` with `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `Content-Disposition: attachment; filename="<slug>-tracker-<ISO_date>.xlsx"`.

### 4.2 Frontend

**`frontend/src/types/index.ts`** — extend
```ts
export interface TaskData {
  id: string;                 // renamed from task_id; back-compat alias kept
  task: string;
  next_step: string;
  status: TopicStatus;
  owner: string;
  added_in_call_id: string | null;
  closed_in_call_id: string | null;
}

export interface OpenQuestionData {
  id: string;
  text: string;
  owner: string;
  status: TopicStatus;        // "open" | "in_progress" | "resolved"
  added_in_call_id: string | null;
  closed_in_call_id: string | null;
}

export interface DecisionData {
  id: string;
  text: string;
  added_in_call_id: string | null;
}

export interface TopicData {
  // ...existing fields...
  open_questions: OpenQuestionData[];
  decisions: DecisionData[];
  chronology_narrative?: string | null;
  rag_verification_note?: string | null;
}

export type ContextScope =
  | "this_call_transcript"
  | "all_call_transcripts"
  | "this_call_topics"
  | "all_project_topics";

export interface LibraryEntry {
  // ...existing...
  context_scope: ContextScope;
}
```

**`frontend/src/components/CallTopicsStage.tsx`** — extend
- Under each topic, render 3 stacked sections: **Tasks** (existing) → **Open questions** (new, amber tint `#fff8e6`) → **Decisions** (new, pale-green tint `#f1f8ee`).
- Each section uses the same inline-edit / add / delete pattern as Tasks.
- Per the approved mockup `phase2-call-topics-extended.html`.

**`frontend/src/components/AddArtifactTypeModal.tsx`** — extend
- Add `<select>` for `context_scope` with 4 labelled options:
  - "This call's transcript" → `this_call_transcript`
  - "All call transcripts (chronological)" → `all_call_transcripts`
  - "This call's topics" → `this_call_topics`
  - "All project topics (incl. previous calls)" → `all_project_topics`
- Default: `this_call_topics`.

**`frontend/src/components/ProjectTrackerTab.tsx`** — NEW (entire tab)
- Per the approved mockup `phase2-project-tracker-tab-v3.html`.
- Renders the 2-sub-tab structure on the Artifacts page; "Project tracker" sub-tab is this component.
- 5 sub-views inside; each with ⓘ popover next to the tab name (info per mockup v3).
- Default sub-view: Dashboard (`#dashboard` URL hash; switchable via tab clicks).
- Export-to-xlsx button at top → `GET /api/projects/{id}/export.xlsx` → browser download.

**`frontend/app/projects/[id]/artifacts/page.tsx`** — refactor
- Add top-level 2-sub-tab nav: "Generate artifacts" (existing flow) | "Project tracker" (new component).

---

## 5. API Design

| Method | Endpoint | Status | Purpose |
|---|---|---|---|
| POST | `/api/calls/{id}/topics/extract_call` (existing) | unchanged | Now outputs v3 schema with open_questions + decisions |
| GET | `/api/calls/{id}/topics/by-call` (existing) | unchanged | Now returns open_questions + decisions + chronology fields |
| POST | `/api/calls/{id}/topics/aggregate` (existing) | extended | At project_updates commit, triggers `chronology_service` for each touched topic |
| **NEW** | `GET /api/projects/{id}/export.xlsx` | **new** | Returns the 5-sheet xlsx as a streaming binary download |
| POST | `/api/artifact-types/` (existing) | extended | Accepts new `context_scope` enum value |
| GET | `/api/library` (existing) | unchanged | Returns the 4-value context_scope |

---

## 6. Key Technical Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Schema sprawl for Phase 2 | New tables (chronology_cells, item_lifecycle) vs reuse topic_updates + JSONB elements | **Reuse + JSONB** | Phase 1 already proved JSONB-on-row works. No new tables = less migration risk + simpler joins. |
| Chronology timing | At export vs at commit (frozen) | **Commit (frozen)** | Cheap exports (no LLM at export). Consistent with PRD G8 + NFR-P2-03 fallback. |
| context_scope: include current call in all_call_transcripts | Yes vs only prior | **Yes (current included)** | Q6 lock. "Summarise across all calls so far" is the dominant use case. |
| xlsx renderer location | Inline in router vs dedicated module | **Dedicated `backend/exporters/xlsx_tracker.py`** | Testable, isolatable, can be reused if a CLI export is added later. |
| Failure mode of chronology LLM | Block commit vs persist marker | **Persist marker (commit succeeds)** | NFR-P2-03. UI can re-trigger if needed. |
| Existing artifact prompt rewrites | Rewrite all 4 vs trust context | **Trust context** | Q4 lock. Cheaper. Smoke-test reveals if rewrites are needed. |
| Per-item lifecycle storage | Separate event table vs in-JSONB | **In-JSONB** | Phase 1 pattern. Atomic with the parent row. |

---

## 7. Integration Seams

| Dependency | Format contract | Known edge cases | Validate before coding |
|---|---|---|---|
| OpenRouter deepseek-v3.2 (chronology) | OpenAI-compatible JSON. Prompt asks for plain text (no JSON wrap). | Model occasionally pads response with explanatory prose. Truncate at first newline or 600 chars. | Dry-run on 1 real (topic, call) pair before locking the prompt. |
| OpenRouter deepseek-v3.2 (RAG verification) | OpenAI-compatible JSON. Plain-text output. | Hallucinated "verified" when narrative is wrong. Mitigation: prompt explicitly asks model to quote the transcript before claiming verified. | Same dry-run. |
| openpyxl | Existing in requirements.txt. Uses BytesIO write. | Long cell values wrap unpredictably — set `wrap_text=True` and column widths explicitly. Multi-line cells need `Alignment(wrap_text=True)`. | Generate 1 xlsx locally before backend ships; open in Excel + Google Sheets to confirm rendering. |
| Frontend file download | `<a download="...">` or `window.location` to the xlsx endpoint. | Browser blocks downloads from cross-origin in some setups — must use same-origin proxy. | Verify via dev server (frontend proxy at port 3015 → backend 8765). |

---

## 8. Performance & Cost

- **Chronology generation at commit:** N_touched_topics × 2 LLM calls. For ~12 topics per call on deepseek-v3.2: ~24 calls × ~3-5s each = **60-120s sequential.** Mitigation: run with `asyncio.gather` parallel (deepseek throughput is fine on 24 concurrent). Target: < 60s per commit (NFR-P2-02).
- **xlsx export:** in-process Python + openpyxl. For 50 topics × 20 calls = 1000 chronology cells: ~ 5-15s render time. Within NFR-P2-01 (30s budget).
- **Per-project LLM cost on a 4-call FactSet smoke test:** ~$0.10-0.20 for all chronology + RAG cells. Negligible.

---

## 9. Known Limitations / Technical Debt

- Chronology narratives are frozen — if extraction is later corrected/re-run, narratives become out-of-sync until a manual re-trigger. Acceptable for v1.
- xlsx is read-only — no round-trip editing. Per PRD NG2.
- "Open questions" status flipping is supported but the v04 reference doesn't show OQ closure UX clearly. Smoke test will reveal if UI needs polish.
- The "Decisions log" sheet has no closure semantics (decisions are immutable). v04 also doesn't track decision revocations.

---

## 10. Platform-Specific Gotchas

- **Supabase migrations are append-only** — migration 027 ships as-is, never edited post-application.
- **openpyxl streaming** — use `Workbook.save(stream)` with a `BytesIO()` then `getvalue()`. Don't write to disk in the request handler.
- **Concurrent chronology generation** — `asyncio.gather` with bounded concurrency (≤ 8 parallel LLM calls) to avoid rate-limit storms on OpenRouter.

---

## 📤 Outputs for Story 5 (Epics & Stories)

**4 stories** map 1:1 with the 4 workstreams:

- **Story 15.5 (P2-A)** — Call-topics extension: open_questions + decisions in prompt + schema + UI (uses extended v3 mockup).
- **Story 15.6 (P2-B)** — context_scope 4-value enum + AddArtifactTypeModal dropdown + backend context-assembly seam + migrate existing library entries.
- **Story 15.7 (P2-C)** — Project tracker state model + per-item lifecycle metadata + chronology + RAG verification services + accumulator on project_updates commit.
- **Story 15.8 (P2-D)** — xlsx_tracker exporter + GET endpoint + ProjectTrackerTab component (uses approved mockup) + smoke-test acceptance.

Dependency order: 15.5 → 15.7 → 15.8 (sequential); 15.6 runs in parallel with any of them.
