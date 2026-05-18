# Architecture — EPIC-15: Call Topics Rebuild

> **Source PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md`
> **Status:** `[x] Draft` → `[ ] Reviewed` → `[ ] Locked`
> Scope: deltas from the project's existing architecture (see `docs/project/config/architecture.md` for the base stack).

---

## 1. Tech Stack — deltas

**No new packages, no new providers, no new services.** Everything below uses what already ships.

| Layer | Choice | Notes |
|---|---|---|
| Backend framework | FastAPI (existing) | — |
| DB | Supabase Postgres (existing) | Single new migration `024_epic15_call_topics_schema.sql` |
| LLM provider | OpenRouter (existing, EPIC-11) | Default model flips to `deepseek/deepseek-v3.2` for system-seed entries only |
| Frontend | Next.js (existing) | No new component library |
| Testing | pytest + jest (existing) | New unit tests on extractor; extended real-fixture test for rollback regression |

---

## 2. System Overview — what changes inside the existing data flow

```
USER (call topics stage UI)                                    USER (project matching UI)
        │                                                                │
        │ 1. opens stage → fetches call + library prompt list            │ 8. opens matching →
        ▼                                                                │    GET aggregate
┌──────────────────────────────┐                                         │    returns topics
│ Prompt-variant selector      │                                         │    + new fields
│ (per-call, persisted on      │                                         ▼
│  calls.call_topics_prompt_id)│                              ┌────────────────────────────┐
└─────────────┬────────────────┘                              │ Matching stage UI          │
              │ 2. user picks prompt                          │ - chips (read-only)        │
              │                                                │ - 📄 evidence popover      │
              ▼                                                │ - tasks summary (read-only)│
┌──────────────────────────────┐                              └────────────────────────────┘
│ POST /api/calls/{id}/extract │
│  → backend extractor          │
│    1. resolves prompt:        │
│       call.prompt_id          │
│       → artifact_library row  │
│    2. calls LLM (OpenRouter)  │
│    3. parses + VALIDATES JSON │
│    4. drops invalid topics    │
│    5. persists topic_updates  │
│       (new shape)             │
└─────────────┬────────────────┘
              │ 3. response with topics array
              ▼
┌──────────────────────────────┐
│ Flat table UI (v3 mockup)    │
│ - inline edits via           │
│   PATCH /api/topics/{id}     │
│ - per-row delete             │
│ - per-topic add/delete       │
│ - hover popover for evidence │
└──────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Backend

**`backend/prompts/call_topics.py`** — gutted
- Delete the `CALL_TOPICS_DEFAULT_PROMPT` constant entirely.
- Keep the file: it now hosts only the **v2 prompt body** as a Python string constant `CALL_TOPICS_V2_PROMPT_BODY`, exported solely for use by `backend/library/seed.py` to populate the new system-default library entry at seed time. Nothing else imports this module.
- Goal: no Python-level fallback. The library is the only source of truth at runtime.

**`backend/library/seed.py`** — updated
- Every entry in `SYSTEM_LIBRARY` that is `kind=llm` or `kind=hybrid` gets its `model` set to `openrouter` and `model_id` to `deepseek-v3.2`. This includes the 4 workflow prompts (`call_topics`, `merge_verification`, `not_discussed_check`, `project_topics`) plus every LLM/hybrid artifact-type entry.
- Add a NEW entry: `name="Call Topics — v2 (synthetic, evidence-anchored)"`, `category=call_topics`, `seeded_by_default=true`, `kind=llm`, body = `CALL_TOPICS_V2_PROMPT_BODY`.
- The pre-existing v1 entry's `seeded_by_default` flips to `false` so the new default is unambiguous; entry itself stays so users can A/B.

**`backend/services/topics_service.py`** — schema + extractor + edit endpoints
- `_TOPIC_SCHEMA` rewritten to the new locked shape (PRD FR-01).
- `TopicIn` / `TopicOut` Pydantic models rewritten; old fields removed (`decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, topic-level `owner`).
- `extract_call_topics(call_id)`:
  1. Resolve prompt: load `calls.call_topics_prompt_id` → fetch `artifact_library` row. If null, load library entry where `category=call_topics AND seeded_by_default=true` (= v2 entry). If neither found → typed error (no Python-side default).
  2. Call LLM via the artifact_library entry's `model` + `model_id`.
  3. Parse JSON. For each topic produced: validate against `_TOPIC_SCHEMA`. Reject topics missing evidence/tasks. Surface reject count.
  4. Persist accepted topics to `topic_updates` with new columns.
- Edit endpoints accept partial `tasks[]` patches (full-array replace; per-task add/delete is a client-driven rebuild of the array). Each task is identified by a `task_id` UUID embedded in the JSONB element when persisted — this is what the row-level delete + status-update endpoints use.

**`backend/routers/topics.py`** — aggregate endpoint
- The endpoint feeding the matching stage now includes `key_terms`, `evidence`, `tasks` in its response shape for each topic. No semantic change to matching logic.

**`backend/routers/calls.py`** — new field on calls
- New endpoint `PATCH /api/calls/{call_id}/prompt-selection` body `{call_topics_prompt_id: UUID|null}`. Persists the per-call prompt choice.
- Alternatively reuse an existing `PATCH /api/calls/{id}` if one exists — decided at implementation.

**`backend/database/migrations/024_epic15_call_topics_schema.sql`** — single migration
```sql
ALTER TABLE topic_updates
  ADD COLUMN evidence  JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN key_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN tasks     JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE topic_updates
  DROP COLUMN IF EXISTS decisions,
  DROP COLUMN IF EXISTS follow_up_items,
  DROP COLUMN IF EXISTS open_questions,
  DROP COLUMN IF EXISTS rationale,
  DROP COLUMN IF EXISTS is_parked,
  DROP COLUMN IF EXISTS owner;

ALTER TABLE calls
  ADD COLUMN call_topics_prompt_id UUID NULL
    REFERENCES artifact_library(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_calls_prompt_id
  ON calls(call_topics_prompt_id);
```

> **Decision on PRD Q1 (drop strategy):** drop in the same migration that adds the new columns. Forward-only, clean break. Existing data in those columns is lost — which is acceptable per PRD NG7 (no migration of existing rows; smoke test uses fresh extractions). No two-step migration window.

**`backend/services/export_service.py`** — untouched.

**Logging delta**: one new structured log line in `extract_call_topics`:
```
📥 [CallTopics] extract call={id} prompt={lib_entry_name} model={provider}/{model_id}
                topics_produced={n_kept} topics_rejected={n_dropped} latency_ms={t}
```

### 3.2 Frontend

**`frontend/src/types.ts`** — reshape `TopicData`
- Add `key_terms: string[]`, `evidence: EvidenceRef[]`, `tasks: TaskData[]`.
- Add `EvidenceRef = { speaker: string, quote: string, citation: string }`.
- Add `TaskData = { task_id: string, task: string, next_step: string, status: 'open'|'in_progress'|'resolved', owner: string }`.
- Remove `decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, topic-level `owner`.
- Add `Call.call_topics_prompt_id: string | null` and `LibraryEntry` already exists.

**`frontend/src/components/CallTopicsStage.tsx`** — full rewrite to v3 layout
- Replace the EPIC-11 `SectionBlock` tile structure.
- New table component renders one row per task with topic + chips repeated on every row.
- Inline edits per cell via PATCH to `/api/topics/{id}` (debounced).
- Per-row × delete task (full tasks array rebuilt and PATCHed).
- Per-topic footer `+ Add task` (push new task with fresh `task_id` UUID, PATCH).
- Per-topic 🗑 Delete topic (DELETE `/api/topics/{id}`, confirm dialog).
- Hover-popover component for evidence (one block per `EvidenceRef`).
- Top of stage: prompt-variant `<select>` populated from `GET /api/library?category=call_topics`. On change, PATCH the call's `call_topics_prompt_id`.

**`frontend/src/components/TopicsDashboard.tsx`** + **`frontend/src/components/TopicsPanel.tsx`** — refactor to read new schema and render the new fields read-only in the matching stage (US-10). chips rendered identically to call_topics stage; evidence popover reused; tasks shown as a compact unordered list with task text + status badge. No edit handlers exposed in the matching view.

**`frontend/src/components/TopicEditor.tsx`** — **DELETE**. Inline edits in the table replace it. (Resolves PRD Q2.)
**`frontend/src/components/TopicEvidenceDrawer.tsx`** — **DELETE**. The styled hover popover absorbs the use case; full-screen drawer is unnecessary.

**`frontend/src/api/client.ts`** — type updates only.

### 3.3 No changes
- Project Matching stage backend code, prompts, aggregate-write paths.
- Per-call markdown export.
- 6 free-text artifact prompts.
- Artifact-pipeline LLM resolution code (other than the system-seed model flip).
- Rollback code path in `KanbanBoard` + `kanban_service`.

---

## 4. Data Model

### `topic_updates` (existing table — schema changes)

```
id              uuid PRIMARY KEY                        (unchanged)
call_id         uuid REFERENCES calls(id)               (unchanged)
project_topic_id uuid                                    (unchanged)
name            text                                    (unchanged)
importance      text  CHECK in (high,medium,low)        (unchanged)
status          text                                    (unchanged — but now driven from tasks roll-up at display time; column kept for back-compat with matching stage)
summary         text                                    (unchanged — narrative summary; kept)
transcript_excerpt text                                  (unchanged — kept; evidence is richer replacement but excerpt stays for now)
evidence        jsonb  NOT NULL DEFAULT '[]'             ← NEW
key_terms       jsonb  NOT NULL DEFAULT '[]'             ← NEW
tasks           jsonb  NOT NULL DEFAULT '[]'             ← NEW
created_at, updated_at                                  (unchanged)

DROPPED: decisions, follow_up_items, open_questions, rationale, is_parked, owner
```

Note: `status` and `summary` columns are retained because today's matching-stage backend reads them. The new shape's de-facto status is per-task, but the legacy column stays populated as a roll-up (e.g., "open" if any task is open, "resolved" if all tasks resolved). This avoids touching the matching stage's input contract — purely backwards-compat.

### `tasks` JSONB element shape
```json
{
  "task_id": "uuid-v4",
  "task": "investigate memory failure",
  "next_step": "Test memory boost flag + FVMAC on Mark's PA",
  "status": "open",
  "owner": "Nick"
}
```

### `evidence` JSONB element shape
```json
{
  "speaker": "Hassan",
  "quote": "…verbatim transcript snippet…",
  "citation": "transcript Apr 13 · lines 145–152"
}
```

### `calls` (existing table — schema change)

```
... (unchanged columns)
call_topics_prompt_id uuid NULL REFERENCES artifact_library(id) ON DELETE SET NULL   ← NEW
```

### `artifact_library` (existing table — no schema change)
- Seed flip: model defaults to `openrouter` + `deepseek-v3.2` on every LLM/hybrid entry.
- New row inserted: `Call Topics — v2 (synthetic, evidence-anchored)`, `category=call_topics`, `seeded_by_default=true`. Existing v1 row's `seeded_by_default` flips to `false`.

---

## 5. API Design — endpoints touched

| Method | Endpoint | Body | Purpose |
|---|---|---|---|
| POST | `/api/calls/{id}/extract` (existing) | `{}` | Resolve prompt from library; run LLM; persist new-shape topics. |
| GET  | `/api/topics?call_id=…` (existing) | — | List topics in new shape. |
| PATCH | `/api/topics/{topic_id}` (existing — expanded) | partial `{name?, importance?, key_terms?, evidence?, tasks?}` | Inline edit any topic-level field; tasks PATCH replaces the full array. |
| DELETE | `/api/topics/{topic_id}` (existing) | — | Delete topic. |
| GET | `/api/library?category=call_topics` (existing) | — | Source for the prompt selector. |
| PATCH | `/api/calls/{id}` (existing — expanded) OR `/api/calls/{id}/prompt-selection` (new) | `{call_topics_prompt_id: uuid|null}` | Persist per-call prompt choice. Implementation picks whichever fits the existing router shape. |
| GET | `/api/topics/aggregate?project_id=…` (existing — payload expanded) | — | Aggregate for matching stage; payload now includes new fields. |

No new endpoints. Existing endpoints expand their payload shape.

---

## 6. Key Technical Decisions

| Decision | Options Considered | Choice | Rationale |
|---|---|---|---|
| Drop strategy for old columns (PRD Q1) | (A) Drop in same migration / (B) Two-step stop-write + DROP later | **A** | Forward-only per PRD NG7. No existing data to preserve (smoke test uses fresh extractions). Avoids zombie-column code drift. |
| TopicEditor / Drawer fate (PRD Q2) | (A) Delete both / (B) Refactor drawer to new schema | **A** — delete both | New inline-edit table + hover popover absorbs both use cases. Reduces frontend surface area. |
| Task identity | (A) Index-based / (B) UUID embedded in JSONB | **B** | Index-based breaks under concurrent re-ordering. UUIDs are stable and 16 bytes. |
| Prompt fallback when library is empty | (A) Hard error / (B) Hidden Python constant fallback | **A** | PRD FR-11: library is the only source of truth. A missing seed is a deployment bug, not a runtime fallback. |
| Status column on `topic_updates` | (A) Drop / (B) Keep + populate as roll-up | **B** | Matching stage reads it. Roll-up at write time = `open` if any task open, else `in_progress` if any in_progress, else `resolved`. Zero new code in matching stage. |
| Model flip blast radius (PRD G8) | (A) Seed only / (B) Sweep all rows / (C) Even overwrite custom rows | **A** | Per Q3 lock = seed only. Existing projects undisturbed. |
| `transcript_excerpt` column | (A) Drop now / (B) Keep | **B** — keep | Used by existing UI components for things outside this epic's surface. Cleanup in a later refactor. |

---

## 7. Integration Seams

| Dependency | Format contract | Known edge cases | Validate before coding |
|---|---|---|---|
| OpenRouter `deepseek/deepseek-v3.2` | OpenAI-compatible JSON; model param string MUST be `deepseek/deepseek-v3.2` (not `deepseek-v3.2`) | Returns occasional ` ```json ` wrapped outputs — strip before JSON.parse. Tokens-per-second varies; budget 90s timeout per extract. | Run a one-call dry extraction against an existing `Factset0204206.txt` transcript via the `/library` system entry's body before locking the v2 prompt rubric. |
| Supabase `artifact_library` table | UUID PK; FK referenced by `calls.call_topics_prompt_id` with ON DELETE SET NULL. | Deleting an in-use library entry leaves call rows with null prompt → they fall back to library default v2. Acceptable. | Run the migration on a dev DB first; verify FK behaves on cascade-test (delete a library entry, observe calls.prompt_id → null). |
| `topic_updates` legacy reads | Any code path still reading `decisions / follow_up_items / open_questions` will break post-migration. | Grep all references before merging the migration. | `rg "decisions|follow_up_items|open_questions|is_parked|rationale" backend/ frontend/src/` and ensure all read paths are migrated. |
| Frontend ⇄ Backend topic schema | New `TopicData` types must align field names exactly with Pydantic `TopicOut`. | Renames (`follow_up_items` → `tasks`) often diverge. | Generate one round-trip test in `backend/tests/test_topics_service.py` that hits PATCH then GET and asserts JSON shape equality. |

---

## 8. Performance Assumptions

- Extraction latency on `deepseek/deepseek-v3.2` via OpenRouter for a single FactSet transcript (≈ 6k–8k tokens) expected 15–35 s. Below the PRD NFR-01 budget of 1.5× today's prompt.
- Topic count per call expected 8–20; rejection rate expected <10% on real transcripts. If rejection >25% in real-fixture testing, the prompt rubric is too strict — adjust before locking.

---

## 9. Known Limitations / Technical Debt

- `topic_updates.summary` + `topic_updates.transcript_excerpt` are kept but not written by the new extractor. Cleanup in a follow-up.
- `topic_updates.status` is a derived roll-up of task statuses; nothing prevents direct writes by other code paths from drifting out of sync. Accepted risk for this epic.
- The v1 call_topics library entry is left in place (`seeded_by_default=false`). It can be reset via `/library`'s "Reset system to defaults" button — that button must NOT re-flip v1 back to default. Implementation note: the reset routine writes `seeded_by_default` based on the seed file, so the seed file's v1 entry must carry `seeded_by_default=false`.

---

## 10. Platform-Specific Gotchas (this epic)

- **Supabase migrations are append-only** — new migration `024_…sql`. Never edit prior migrations. PRD-locked.
- **JSONB default values must be cast** — `'[]'::jsonb` not `'[]'`. Same for `'[]'::jsonb` on the three new columns (already in the migration above).
- **OpenRouter model IDs are case-sensitive** — `deepseek/deepseek-v3.2` exact form. Tested at first integration point.

---

## 📤 Outputs for Step 4 (Logging) and Step 5 (Epics & Stories)

- **Step 4 (Logging):** one new log line shape in `extract_call_topics` (see §3.1). Existing logging infrastructure handles it; no `4-LOGGING.md` re-write needed.
- **Step 5 (Stories):** the component breakdown above suggests **4 stories** for the epic build:
  1. **Story 15.1** — DB migration + backend schema/services rewrite (extractor + edit endpoints + prompt resolution from library).
  2. **Story 15.2** — Library seed: model defaults flip + add v2 call_topics entry + v1 demoted.
  3. **Story 15.3** — Call Topics stage UI rewrite (v3 layout + inline edits + popover + prompt selector). Delete `TopicEditor.tsx` + `TopicEvidenceDrawer.tsx`.
  4. **Story 15.4** — Project Matching stage UI: surface `key_terms` / `evidence` / `tasks` read-only. Real-fixture acceptance + rollback regression test.
