# PRD — EPIC-15 Phase 2: Artifacts Rebuild + xlsx Tracker Export

> **Source brainstorm:** `docs/project/config/2026-05-18-epic-15-phase-2-brainstorm.md` (status: GO)
> **Status:** `[x] Draft` → `[ ] Reviewed` → `[ ] Locked`
> ⚠️ Once LOCKED, changes require a dated amendment at the bottom.

---

## 1. Project Summary
| Field | Value |
|---|---|
| **Project name** | EPIC-15 Phase 2 — Artifacts rebuild + xlsx tracker |
| **One-liner** | Per-project xlsx tracker (`FactSet_SWIB_RAM_Tracker_v04`-shaped) that accumulates correctly across calls + flexible custom-artifact creation with 4-value context scope. |
| **Owner** | Louis |
| **Target completion** | Same sprint as Phase 1 — user has flagged "I want this done quickly" |
| **Tech stack** | Unchanged from Phase 1. openpyxl already in `requirements.txt` (used by EPIC-12). No new packages. |

---

## 2. Goals & Non-Goals

### ✅ Goals (In Scope)

- **G1.** Call_topics extraction emits `open_questions[]` and `decisions[]` alongside `tasks[]` — single LLM round-trip, three structured arrays. The DUAL-CLASSIFY rule applies: an action phrased as "investigate / verify / check" goes into BOTH `tasks[]` AND `open_questions[]`.
- **G2.** Each item in `tasks` / `open_questions` / `decisions` carries lifecycle metadata: `added_in_call_id` (UUID, set at first insertion), `closed_in_call_id` (UUID|null, set when status flips to resolved for tasks/open_questions). Decisions are immutable once committed; their "added_in" equals their "decided_in".
- **G3.** Call Topics stage UI extended: under each topic in the v3 table layout, three sections render — Tasks (existing), Open questions (new), Decisions (new). Each section is inline-editable per Phase 1 patterns.
- **G4.** `context_scope` on `artifact_library` becomes a 4-value enum: `this_call_transcript` / `all_call_transcripts` / `this_call_topics` / `all_project_topics`. Every existing library entry is migrated to its correct scope value.
- **G5.** `AddArtifactTypeModal` (frontend) gains a context-scope dropdown so user-added artifacts pick their scope. Existing modal flow otherwise unchanged.
- **G6.** Backend artifact-generation engine assembles the LLM context per scope before calling the model. All 4 scope values produce non-empty, semantically-correct context.
- **G7.** `project_updates` stage (kanban) accumulates per-call data into project-level state: tasks/open_questions/decisions appended with lifecycle metadata; `key_terms` unioned per topic; evidence appended per (project_topic, call); one chronology cell row per (project_topic, call) committed at this stage.
- **G8.** A "chronology cell" LLM artifact runs at project_updates commit for every (project_topic, call) pair touched in that call. Output = narrative paragraph (frozen after commit) + RAG verification note (frozen after commit; second LLM call audits the narrative against the actual transcript text for that topic).
- **G9.** Artifacts page is restructured into **2 sub-tabs**:
  - **"Generate artifacts"** — existing library-driven flow (cards + AddArtifactTypeModal).
  - **"Project tracker"** — 5 read-only sub-views (Dashboard, Chronology, Anchors lifecycle, Decisions log, Key terms registry) + Export-to-xlsx button at top.
- **G10.** Clicking Export-to-xlsx on the Project tracker sub-tab downloads a `<project_slug>-tracker-<ISO_date>.xlsx` file with 5 sheets matching v04 shape (Dashboard / Chronology / Anchors lifecycle / Decisions log / Key terms registry). openpyxl renderer in `backend/exporters/xlsx_tracker.py`.
- **G11.** Real-fixture acceptance: 4 FactSet transcripts run end-to-end on smoke-test project (`17e2687f-bdd8-43ee-88a7-d2bd79a13925`). After all 4 calls reach `done`, the exported xlsx shows accumulated data: topics that appeared in multiple calls have multiple chronology cells, tasks with `Added in` and `Closed in` lifecycle, decisions with `Decided in` dates, key_terms unioned across calls.

### ❌ Non-Goals (Out of Scope — AI must not implement these)

- **NG1.** Status review sheet — dropped. xlsx has 5 sheets, not 6.
- **NG2.** xlsx round-trip editing (user edits the file → re-imports). Read-only export.
- **NG3.** Charts, conditional formatting, pivot tables in the xlsx beyond what v04 visibly contains. Plain tables only.
- **NG4.** Auto-close / auto-archive of stale topics. Silent-call counter is implicitly computed (last_touched_call_id − current_call_id) but no action taken on it.
- **NG5.** Migration of pre-Phase-1 historical data into the new tracker shape. Forward-only. Smoke-test uses fresh extractions.
- **NG6.** Project Matching prompt or auto-suggestions. Matching stays user-driven manual per Phase 1.
- **NG7.** Deletion of the existing Topics tab on the project board. Stays in place for visual comparison during smoke. Retirement decision deferred to post-Phase-2 evaluation.
- **NG8.** A separate "Ad-hoc prompt" feature. The 4-value context_scope on AddArtifactTypeModal IS the ad-hoc path.
- **NG9.** New LLM provider. OpenRouter + deepseek/deepseek-v3.2 continues as default per Phase 1.
- **NG10.** Editing the Project tracker sub-tab contents (Dashboard / Chronology / etc.). The sub-tab is **read-only**; edits go through the Call Topics stage or project_updates stage.

---

## 3. User Stories

### Must Have (MVP)

| ID | Story | Acceptance Criteria |
|---|---|---|
| **US-P2-01** | As an analyst, I want the call_topics extraction to also produce open questions and decisions so I can track all three anchor types per call. | - [ ] Extract response carries `open_questions[]` AND `decisions[]` AND `tasks[]` per topic <br> - [ ] DUAL-CLASSIFY rule observable: any "investigate/verify/check" task also appears in `open_questions[]` <br> - [ ] Each item has `added_in_call_id` set |
| **US-P2-02** | As an analyst, I want to see open questions + decisions inline on the Call Topics stage so I can review and edit all three sections at once. | - [ ] v3 table layout shows 3 sections per topic: Tasks / Open questions / Decisions <br> - [ ] All three are inline-editable (add / delete / edit row) per Phase 1 patterns <br> - [ ] Empty section collapses gracefully (doesn't bloat the row) |
| **US-P2-03** | As an analyst, I want to add a custom artifact type with my own prompt and choose which context the LLM sees, so I can ask ad-hoc questions about any scope of project data. | - [ ] AddArtifactTypeModal has a context-scope dropdown with 4 options <br> - [ ] Each option maps to a clearly-labelled context (this call's transcript, all transcripts, this call's topics, all project topics) <br> - [ ] After creating the custom type, running it produces output using ONLY the chosen scope's context |
| **US-P2-04** | As an analyst, I want the existing 4 LLM artifacts to keep generating useful content even though the legacy schema fields are empty. | - [ ] Executive Summary regenerates referencing tasks/open_questions/decisions/key_terms from the new schema <br> - [ ] Same for Email Summary, Email Follow-up, Next Call Agenda <br> - [ ] No artifact produces empty output for a real FactSet call |
| **US-P2-05** | As an analyst, after I finalise project_updates for a call, I want each touched topic to accumulate into a project-level tracker so the project view shows running state across calls. | - [ ] Project topic's `tasks[]` / `open_questions[]` / `decisions[]` grow across calls <br> - [ ] `key_terms[]` is unioned across calls per topic <br> - [ ] `evidence[]` is appended per (topic, call) <br> - [ ] Lifecycle metadata (added_in / closed_in) populated correctly for new + resolved items |
| **US-P2-06** | As an analyst, I want a per-(topic, call) chronology narrative paragraph + a RAG verification note so the xlsx Chronology sheet reads cleanly. | - [ ] At project_updates commit, every touched topic gets one chronology cell row <br> - [ ] Cell carries `narrative` (LLM-written) + `rag_verification_note` (second LLM call auditing against transcript) <br> - [ ] Both are frozen after commit — never regenerated on export |
| **US-P2-07** | As an analyst, I want a "Project tracker" sub-tab on the Artifacts page where I can see 5 read-only views of the accumulated state. | - [ ] Artifacts page shows 2 sub-tabs at top: "Generate artifacts" (existing flow) + "Project tracker" (new) <br> - [ ] Project tracker sub-tab renders 5 sub-views: Dashboard / Chronology / Anchors lifecycle / Decisions log / Key terms registry <br> - [ ] Each sub-view is read-only — no inline edits |
| **US-P2-08** | As an analyst, I want an Export-to-xlsx button so I can download a `FactSet_SWIB_RAM_Tracker_v04`-shaped file. | - [ ] Export button visible at top of Project tracker sub-tab <br> - [ ] Click → browser downloads `<project_slug>-tracker-<ISO_date>.xlsx` <br> - [ ] File opens cleanly in Excel; has 5 sheets named per v04; each sheet's columns match v04 |
| **US-P2-09** | As an analyst, I want the real-fixture test to drive 4 FactSet transcripts through the full pipeline end-to-end and produce a non-empty tracker xlsx. | - [ ] `backend/tests/test_real_fixture_4calls.py` (gated `@pytest.mark.realfixture`) extended <br> - [ ] After all 4 calls reach `done`, exported xlsx has 5 non-empty sheets <br> - [ ] Topics that appeared in multiple calls have multiple chronology cells <br> - [ ] At least one task in Anchors lifecycle has both `Added in` AND `Closed in` populated |

---

## 4. Functional Requirements

- **FR-P2-01.** `extract_call_topics` JSON output adds two arrays per topic: `open_questions: [{text, ...}]` and `decisions: [{text, ...}]`. Both are required (`>= 0` items allowed; `[]` is valid).
- **FR-P2-02.** Each task / open_question / decision item is stamped at persistence with: `id` (UUID, generated like `task_id` is today), `added_in_call_id` (= current call_id). `closed_in_call_id` defaults to `null`; flips to current call_id when the item's `status` changes from open/in_progress → resolved (tasks + open_questions only — decisions have no status).
- **FR-P2-03.** Schema migration (next available migration number): ADD `topic_updates.open_questions JSONB NOT NULL DEFAULT '[]'::jsonb`, `topic_updates.decisions JSONB NOT NULL DEFAULT '[]'::jsonb`, `topic_updates.chronology_narrative TEXT`, `topic_updates.rag_verification_note TEXT`. (Lifecycle metadata stored within the existing tasks JSONB elements — no new columns needed.)
- **FR-P2-04.** `context_scope` constraint on `artifact_library` updated: CHECK in (`this_call_transcript`, `all_call_transcripts`, `this_call_topics`, `all_project_topics`). Seed migration converts existing values: `"call"` → `this_call_topics`; `"project"` → `all_project_topics`. The 4 LLM artifacts get explicit values: Executive Summary = `this_call_topics`, Email Summary = `this_call_topics`, Email Follow-up = `this_call_topics`, Next Call Agenda = `all_project_topics`.
- **FR-P2-05.** Backend artifact-generation function gets a context-assembly seam: given an artifact_type's `context_scope`, it builds the LLM prompt context from:
  - `this_call_transcript` → only the current call's transcript text
  - `all_call_transcripts` → concatenated transcripts of every call in the project (chronological)
  - `this_call_topics` → only this call's topic_updates rows (new shape)
  - `all_project_topics` → all topic_updates rows for all topics in this project (chronological by call)
- **FR-P2-06.** `AddArtifactTypeModal` displays a context-scope `<select>` with 4 labelled options. Submitting the modal writes the chosen scope into the new artifact_type row.
- **FR-P2-07.** `project_updates` stage acceptance handler is upgraded to merge call-level data into project-level state:
  - For each project topic touched: append items from this call's `tasks` / `open_questions` / `decisions` (with lifecycle stamps), union `key_terms`, append evidence.
  - Insert one `chronology_cell` per (project_topic, call) by triggering the chronology-cell artifact below.
- **FR-P2-08.** New "chronology cell" generation: 1 LLM call per (touched_topic, this_call) producing a 2-3 sentence narrative paragraph summarising what happened to that topic in this call. Persists to `topic_updates.chronology_narrative`. Frozen after commit (never re-run).
- **FR-P2-09.** New "RAG verification" generation: 1 LLM call per chronology cell that audits the narrative against the actual transcript snippet evidence for that topic. Output = short note ("verified" / "X drifted from transcript: ..."). Persists to `topic_updates.rag_verification_note`. Frozen.
- **FR-P2-10.** New backend endpoint: `GET /api/projects/{project_id}/export.xlsx` returns the rendered xlsx as a streaming binary response with appropriate `Content-Disposition` header. Implementation: `backend/exporters/xlsx_tracker.py` using openpyxl.
- **FR-P2-11.** Frontend: new "Project tracker" sub-tab on `/projects/[id]/artifacts` (or wherever the existing Artifacts page lives). 5 sub-views rendered as tables (use the existing `KeyTermChips` + `EvidenceRefPopover` for cell-level chips/evidence). Top of sub-tab: Export-to-xlsx button.
- **FR-P2-12.** All read paths that fetch topic data must now include `open_questions, decisions, chronology_narrative, rag_verification_note` in their SELECTs and return them on the response. Same sweep pattern as Phase 1.

---

## 5. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| **NFR-P2-01** | Performance | xlsx export must complete within 30s for a project with ≤ 50 topics × ≤ 20 calls. |
| **NFR-P2-02** | Performance | Chronology-cell + RAG-verification generation at project_updates commit must complete within 60s for a call touching ≤ 30 topics. (Parallel LLM calls if needed; deepseek/deepseek-v3.2 is fast.) |
| **NFR-P2-03** | Reliability | Failed chronology-cell LLM call MUST NOT block project_updates from completing. Failure persists `chronology_narrative = ""` and `rag_verification_note = "(generation failed)"` so the commit succeeds and the sheet renders a clearly-marked empty cell. |
| **NFR-P2-04** | Reliability | `_persist_topic_update` and the new accumulator must be idempotent on re-save (delete-then-insert pattern from EPIC-15 Phase 1). |
| **NFR-P2-05** | Observability | One structured log line per chronology-cell + per RAG-verification call: `📥 [Chronology] topic={id} call={id} model=... latency_ms=... bytes=...`. |
| **NFR-P2-06** | Compatibility | Existing per-call markdown export (`/api/calls/{id}/export`) stays untouched. xlsx export is additive. |
| **NFR-P2-07** | Security | xlsx export endpoint returns only data the user has access to (same project-scoping as the existing topics endpoints). |

---

## 6. Data Requirements

| Dataset | Source | Format | Volume | Refresh |
|---|---|---|---|---|
| `topic_updates` (existing) | Supabase | Postgres + JSONB | ~10–50 rows per call | Per extraction + per project_updates commit |
| `artifact_library` (existing) | Supabase | Postgres | ~8 system + N user | Edited via /library UI |

**Schema changes (forward-only):**
- ADD `topic_updates.open_questions JSONB NOT NULL DEFAULT '[]'::jsonb`
- ADD `topic_updates.decisions JSONB NOT NULL DEFAULT '[]'::jsonb`
- ADD `topic_updates.chronology_narrative TEXT`
- ADD `topic_updates.rag_verification_note TEXT`
- ALTER `artifact_library.context_scope` CHECK constraint to the 4-value enum; seed-migrate existing values
- Each tasks / open_questions / decisions JSONB element gains: `id` (UUID), `added_in_call_id` (UUID), `closed_in_call_id` (UUID|null for tasks/open_questions; omitted for decisions)

**Data constraints:**
- Raw transcripts READ ONLY (existing).
- No PII beyond what transcripts already contain.

---

## 7. Interfaces & Integrations

No new external systems. Existing OpenRouter + deepseek-v3.2 handles the new chronology + RAG verification LLM calls.

| System | Direction | Method | Auth |
|---|---|---|---|
| Supabase (Postgres) | Read/Write | supabase-py client | `.env` (existing) |
| OpenRouter | Outbound | OpenAI-compatible SDK | `.env` (existing) |

---

## 8. Error Handling Policy

- LLM call failure (chronology, RAG, or generation): persist a clearly-marked empty result (`narrative=""`, `rag_note="(generation failed)"`) so the pipeline doesn't block. UI shows the failed cell explicitly so the user can re-run.
- xlsx generation failure (e.g. openpyxl error on malformed data): return HTTP 500 with structured error body; frontend shows a non-blocking toast.
- AddArtifactTypeModal validation failure: standard inline form error per existing pattern.
- Concurrent edits during project_updates: last-write-wins per existing convention.

---

## 9. Constraints

- Python 3.10+ (existing).
- openpyxl already in `requirements.txt` (used by EPIC-12 + earlier).
- All git via `python3 scripts/git_ops.py`. Commit format `[EPIC-15] type: short description`.
- New migration goes in `backend/database/migrations/` with the next available number.
- Real-fixture acceptance is mandatory (per project CLAUDE.md): the 4 FactSet transcripts must run end-to-end and produce a non-empty xlsx before Phase 2 can close.

---

## 10. Open Questions (resolve at Architecture step or earlier)

| # | Question | Owner | Deadline | Answer |
|---|---|---|---|---|
| **Q1** | Lifecycle metadata `closed_in_call_id`: does flipping status open → in_progress → resolved → in_progress → resolved write a NEW closed_in_call_id (latest), or keep the FIRST closure? | Louis | Architecture | _open_ |
| **Q2** | Chronology cell length cap: max characters / sentences for the LLM narrative? (V04 cells are 2-3 sentences ≈ 200-400 chars.) | Louis | UI mockup | _open_ |
| **Q3** | Project tracker sub-tab default view (which sub-view loads first when user clicks the sub-tab)? Dashboard probably. | Louis | UI mockup | _open_ |
| **Q4** | Existing 4 LLM artifact prompts (Executive Summary, etc.) — rewrite their bodies to reference new fields, or accept that they render the new shape via the context engine without prompt changes? Lean toward: keep prompts as-is, let context_scope deliver new-shape data. | Louis | Architecture | _open_ |
| **Q5** | xlsx filename format: `<project_slug>-tracker-<ISO_date>.xlsx` vs `<project_name>-tracker-<date>.xlsx`. | Louis | Architecture | _open_ |
| **Q6** | "All call transcripts" context scope: include the current call as well, or only PRIOR calls? Lean toward: include current call (most useful for "summarise across all calls so far" prompts). | Louis | Architecture | _open_ |

---

## 📝 Amendments Log
_Empty — initial draft._

---

## 📤 Outputs for UI mockups + Architecture

**Mockups required (BEFORE architecture lock):**
- v3 tile extension: how `open_questions[]` + `decisions[]` sections render under each topic in the Call Topics stage table.
- Project tracker sub-tab: 5 sub-views layout + Export-to-xlsx button + sub-tab navigation on Artifacts page.

**Architecture inputs from this PRD:**
- Schema migration outline (§6) → architecture finalises column types + indexes
- FR-P2-05 (context-assembly seam) → architecture defines the function signature + call sites
- FR-P2-08 + FR-P2-09 (chronology + RAG) → architecture defines whether they run sequentially or in parallel, and where in the project_updates handler they trigger
- FR-P2-10 (xlsx renderer) → architecture defines the file structure for `backend/exporters/`
