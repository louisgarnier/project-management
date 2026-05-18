# PRD — EPIC-15: Call Topics Rebuild

> **Source brainstorm:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-brainstorm.md` (status: GO)
> **Status:** `[x] Draft` → `[ ] Reviewed` → `[ ] Locked`
> ⚠️ Once LOCKED, changes require a dated amendment at the bottom.

---

## 1. Project Summary
| Field | Value |
|---|---|
| **Project name** | EPIC-15 — Call Topics Rebuild |
| **One-liner** | Replace today's verbose, drifting call-topics output with sharp, evidence-anchored topics that map to clear tasks[], surfaced in a row-per-task UI with full inline editing. |
| **Owner** | Louis |
| **Target completion** | Within current sprint — user has flagged "I want this done quickly" |
| **Tech stack** | Unchanged from `prd.md` (FastAPI + Supabase + Next.js). No new packages. |

---

## 2. Goals & Non-Goals
> *This section is LAW for the AI. It will not build non-goals.*

### ✅ Goals (In Scope)
- **G1.** New `call_topics` prompt produces topics that are short, synthetic, and anchored to ≥1 verbatim transcript quote — no padding, no drift, no speculation.
- **G2.** Each topic carries `name`, `importance`, `key_terms[]`, `evidence[]`, `tasks[]` — schema enforced at extraction time (invalid topics rejected, not silently coerced).
- **G3.** Each task carries `task`, `next_step`, `status (open/in_progress/resolved)`, `owner (optional)`. Status lives on the task, not the topic.
- **G4.** Call Topics stage UI renders one row per task with the topic name + key-term chips repeated on every row, and a styled hover popover for evidence (v3 mockup, locked).
- **G5.** Every field is editable inline (in the **call topics stage only**): topic name, importance, key_terms (add/remove), evidence (add/remove/edit), task text, next_step text, owner, status; add/delete task within a topic; delete whole topic.
- **G6.** Project-matching stage **reads** the new topic fields (`key_terms`, `evidence`, `tasks`) and surfaces them **read-only** in its UI so the user can use them while doing manual matching. No edit affordance there. No change to matching logic / no new matching prompt / no auto-suggestions.
- **G7.** Call-topics prompt is **selectable per-call from the artifact library**. When the user enters the call_topics stage (arrives or opens the tile), a prompt-variant selector is visible; selection is per-call (not per-project, not per-extraction-run). The hard-coded `CALL_TOPICS_DEFAULT_PROMPT` constant in `backend/prompts/call_topics.py` is removed; prompt resolution reads from the artifact library only.
- **G8.** **Artifact library system defaults** (the system-seed entries) flip their default model to `openrouter / deepseek-v3.2` for all LLM and hybrid kinds, including the workflow prompts (`call_topics`, `merge_verification`, `not_discussed_check`, `project_topics`). **Scope is system seed only** — existing projects' `default_model` and existing artifact_type rows are NOT modified.
- **G9.** Rollback semantics preserved verbatim: re-running call_topics on call N rolls back later calls to the call_topics stage. Regression test on the 4-FactSet-transcript fixture covers this.
- **G10.** Real-fixture acceptance: running the 4 FactSet transcripts (`Factset0204206.txt`, `Factset13042026.txt`, plus 2 others in the smoke-test project) through the new pipeline produces topics visibly tighter than today's EPIC-11 output.

### ❌ Non-Goals (Out of Scope — AI must not implement these)
- **NG1.** xlsx export of any kind.
- **NG2.** Decisions log / Status review / Chronology / Key-terms registry sheet — none.
- **NG3.** Changes to the per-call markdown export (`backend/services/export_service.py`). Untouched.
- **NG4.** Artifact-pipeline changes for the 6 free-text artifacts (executive summary, next steps, questions, 2× emails, agenda). Those artifacts stay as they are today. (G7/G8 only touch the workflow-prompt entries.)
- **NG5.** Project-matching **logic** changes — input contract semantics, matching prompt (there isn't one — matching is manual), auto-suggestions, or any edit affordance on the new fields in the matching UI. Surfacing the new fields read-only (G6) is the only matching-stage change.
- **NG6.** Owner-roster / people-management. Owner is plain free-text on each task.
- **NG7.** Backfill or migration of existing `topic_updates` rows. Forward-only.
- **NG8.** Empty-tasks handling. A topic with zero tasks is rejected at extraction.
- **NG9.** New LLM provider. OpenRouter is already integrated (EPIC-11). Only the default-model flip per G8.
- **NG10.** Modification of any existing project's `default_model` or any existing artifact_type row's `model`. G8 is **system-seed only**.
- **NG11.** Project-level prompt-variant default. Selector is per-call only.
- **NG12.** Importance-based sort, status-based filter, or any other client-side ordering of topics. Render in prompt order.

---

## 3. User Stories

> *All stories below are MVP. There is no "Should Have" or "Nice to Have" for this epic.*

### Must Have (MVP)

| ID | Story | Acceptance Criteria |
|---|---|---|
| **US-01** | As an analyst, I want extracted topics that are short and tied to verbatim quotes, so I can trust they reflect what was said. | - [ ] Every topic carries ≥1 evidence reference with speaker + quote + citation <br> - [ ] Average topic name length on 4 FactSet transcripts is visibly shorter than today's EPIC-11 output <br> - [ ] No topic is created without an anchoring quote |
| **US-02** | As an analyst, I want each task on its own row with the topic name + chips repeated, so I can scan every action at a glance. | - [ ] One row per task <br> - [ ] Topic name + chips visible on every row of that topic <br> - [ ] Columns: Topic/chips, Task, Next step, Owner, Status, Evidence, Actions |
| **US-03** | As an analyst, I want to edit any field inline, so I can fix prompt mistakes without re-extracting. | - [ ] Topic name, importance, key_terms (add/remove), evidence (add/remove/edit), task text, next_step text, owner text all editable inline <br> - [ ] Edits persist to DB via the topic service <br> - [ ] No "save" button required per field — autosave on blur/change |
| **US-04** | As an analyst, I want to change task status via dropdown, so I can mark progress without leaving the row. | - [ ] Status dropdown shows OPEN / IN PROGRESS / RESOLVED <br> - [ ] Selection persists immediately <br> - [ ] Badge colour reflects new value |
| **US-05** | As an analyst, I want to add and delete tasks within a topic, so the final state matches reality. | - [ ] "+ Add task to <topic>" button at end of each topic group <br> - [ ] Per-row × deletes that task only <br> - [ ] Topic remains valid if it still has ≥1 task; if last task is deleted, user is asked to delete the topic |
| **US-06** | As an analyst, I want to delete a whole topic, so I can drop hallucinations or merge-duplicates. | - [ ] 🗑 Delete topic button at end of each topic group <br> - [ ] Confirmation dialog before deletion <br> - [ ] All tasks of that topic removed from DB |
| **US-07** | As an analyst, I want to see the verbatim quotes behind a topic, so I can verify the LLM's reasoning. | - [ ] 📄 evidence indicator on every row <br> - [ ] Hover opens a styled popover (white background, soft border) <br> - [ ] Each reference rendered with speaker bold, quote italic, citation small grey <br> - [ ] Popover supports multiple references per topic |
| **US-08** | As an analyst, I want re-running call_topics on a call to roll back later calls to call_topics stage, so my pipeline state stays consistent. | - [ ] Regression test in `backend/tests/test_real_fixture_4calls.py` re-runs extraction on call 2 and asserts calls 3 + 4 are in `call_topics` stage <br> - [ ] Test passes on every CI run |
| **US-09** | As an analyst, I want the project-matching stage to keep working with the new topics, so my downstream flow is uninterrupted. | - [ ] Smoke-test project completes through project-matching with new-shape topics <br> - [ ] Manual matching UI renders without error |
| **US-10** | As an analyst doing manual project matching, I want to see each topic's key_terms, evidence, and tasks **read-only**, so I can make better matching decisions without going back. | - [ ] Matching UI renders chips, 📄 evidence popover (same styling as call_topics stage), and a compact tasks summary for each topic <br> - [ ] No edit affordance on any of these fields in the matching UI <br> - [ ] Visible by default — no extra click needed |
| **US-11** | As an analyst arriving at the call_topics stage, I want to pick which prompt variant to use for this call's extraction, so I can experiment with prompt versions without code changes. | - [ ] Prompt-variant selector visible when the stage opens or tile expands <br> - [ ] Selector lists all `call_topics`-category entries from the artifact library <br> - [ ] Selection is **per-call** (stored on the call), not per-project <br> - [ ] Running extraction uses the selected prompt; if none selected, falls back to library system default |
| **US-12** | As an admin / first-time-user, I want new projects to get `openrouter / deepseek-v3.2` as the default model on every workflow prompt + LLM/hybrid artifact, so new projects are immediately on the recommended model. | - [ ] Artifact library system-seed entries set `model = openrouter`, `model_id = deepseek-v3.2` for every LLM/hybrid kind including the 4 workflow prompts <br> - [ ] Re-running "Reset system to defaults" on `/library` flips a fresh DB to these values <br> - [ ] Existing projects are untouched |

---

## 4. Functional Requirements

- **FR-01.** `extract_call_topics` shall produce JSON matching the locked schema: `{name, importance ∈ {high,medium,low}, key_terms: string[]≥1, evidence: {speaker, quote, citation}[]≥1, tasks: {task, next_step, status ∈ {open,in_progress,resolved}, owner?: string}[]≥1}`.
- **FR-02.** `extract_call_topics` shall reject and log any topic missing `evidence` (zero refs), missing `tasks` (zero tasks), or with any task missing `task`/`next_step`/`status`. Rejected topics are dropped, not coerced. Rejection counts are surfaced in extraction logs.
- **FR-03.** The system shall NOT write `decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, or the old topic-level `owner` enum for any new topic_updates row.
- **FR-04.** The Call Topics stage UI shall render the v3 layout (`call-topic-tile-v3.html`): one row per task, topic + chips repeated per row, columns Topic/Task/Next step/Owner/Status/Evidence/Actions.
- **FR-05.** The UI shall provide inline-edit affordances for every locked-editable field; each edit persists via PATCH to the topic service.
- **FR-06.** The UI shall provide "+ Add task to <topic>", per-row "× Delete task", and "🗑 Delete topic" actions.
- **FR-07.** Evidence indicator shall open a styled popover on hover; popover renders one block per reference.
- **FR-08.** Re-running call_topics extraction on call N shall roll back calls > N to the call_topics stage. No change to current rollback code path.
- **FR-09.** The aggregate endpoint feeding the project-matching stage shall include the new fields (`key_terms`, `evidence`, `tasks`) in its response payload. The matching-stage UI shall render `key_terms` (chips), `evidence` (styled popover, same component as call_topics stage), and `tasks` (compact summary, read-only) for every topic. No edit handler.
- **FR-10.** Extraction shall log: input transcript length, topic count produced, topic count rejected with reason, total LLM round-trip latency, model name, prompt variant used. Format per existing convention (`📥 [CallTopics] ...`).
- **FR-11.** The hard-coded `CALL_TOPICS_DEFAULT_PROMPT` constant in `backend/prompts/call_topics.py` shall be removed. Prompt resolution at extraction time: (1) call's selected `call_topics_prompt_id` → (2) artifact library entry where `category=call_topics` AND `seeded_by_default=true`. No code fallback constant.
- **FR-12.** The call_topics stage UI shall expose a prompt-variant dropdown listing all artifact library entries where `category=call_topics`. Selection persists as `calls.call_topics_prompt_id` (FK to `artifact_library.id`) on the call. Dropdown is visible when the stage opens or the tile is expanded.
- **FR-13.** Artifact library seed (`backend/library/seed.py` `SYSTEM_LIBRARY`) shall set `model=openrouter`, `model_id=deepseek-v3.2` for every LLM and hybrid kind, including the 4 workflow-prompt entries (`call_topics`, `merge_verification`, `not_discussed_check`, `project_topics`). System seed only — no migration of existing rows.
- **FR-14.** A NEW v2 call_topics prompt entry shall be added to `SYSTEM_LIBRARY` named (e.g.) `Call Topics — v2 (synthetic, evidence-anchored)`. Its prompt body is the rewrite specified in this epic. The pre-existing v1 entry stays in the library so users can compare.

---

## 5. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| **NFR-01** | Performance | New prompt's end-to-end extraction wall-clock per call within 1.5× of today's EPIC-11 prompt on the same model. Acceptance: timed runs on the 2 FactSet transcripts. |
| **NFR-02** | Reliability | Invalid LLM output (malformed JSON, missing required fields) is rejected with a typed error surfaced in the UI as a re-extract suggestion. No silent partial saves. |
| **NFR-03** | Reliability | Existing rollback regression covered by the new test in `test_real_fixture_4calls.py`. Test gated `@pytest.mark.realfixture` per CLAUDE.md rule. |
| **NFR-04** | Observability | Every extraction emits one structured log line: timestamp, call_id, model, topic_count, rejected_count, latency_ms. |
| **NFR-05** | Compatibility | Project-matching aggregate endpoint contract unchanged (FR-09). |
| **NFR-06** | Security | No new credentials, no new external services. Prompt content does not leak transcript outside the call-tracker pipeline. |
| **NFR-07** | DB schema | All `topic_updates` schema changes via a single new migration file in `backend/database/migrations/`. Number = next available. |

---

## 6. Data Requirements

| Dataset | Source | Format | Volume | Refresh |
|---|---|---|---|---|
| `topic_updates` (existing table) | Supabase | Postgres / JSONB | ~10–50 rows per call | Per extraction |

**Schema changes (forward-only):**
- ADD `evidence JSONB NOT NULL DEFAULT '[]'::jsonb` to `topic_updates`
- ADD `key_terms JSONB NOT NULL DEFAULT '[]'::jsonb` to `topic_updates`
- ADD `tasks JSONB NOT NULL DEFAULT '[]'::jsonb` to `topic_updates`
- ADD `call_topics_prompt_id UUID NULL` to `calls` (FK to `artifact_library.id`, nullable; null = use library default)
- DROP (or stop writing — decided at Architecture step): `decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, `owner` (the old topic-level enum). Exact drop strategy is Open Question Q1.
- UPDATE `SYSTEM_LIBRARY` seed: model defaults flip to `openrouter / deepseek-v3.2` for every LLM and hybrid entry. Add new v2 call_topics entry alongside the v1 entry.

**Data constraints:**
- Raw transcripts are READ ONLY.
- No PII handling beyond what the existing system already does. Speaker names already appear in transcripts; same convention.

---

## 7. Interfaces & Integrations

| System | Direction | Method | Auth |
|---|---|---|---|
| Supabase (Postgres) | Read/Write | supabase-py client | `.env` |
| LLM provider (existing default — OpenRouter per project default) | Outbound | OpenAI-compatible SDK | `.env` |

No new integrations.

---

## 8. Error Handling Policy

- LLM returns malformed JSON → extraction fails fast, returns a typed error to the UI ("LLM produced invalid output — re-run extraction"); no partial save.
- LLM returns a topic without evidence/tasks → that topic is dropped, others persist. Drop count surfaced in the UI footer.
- User edit conflict (concurrent edits on the same topic) — last-write-wins, per existing app convention.
- Re-extraction roll-back errors → existing error path; no change to current behaviour.

---

## 9. Constraints

- Python 3.10+ (existing).
- No new packages without Architecture-step approval.
- No raw `git` commands — all git via `python3 scripts/git_ops.py`.
- Commit format `[EPIC-15] type: short description`.
- New migrations go in `backend/database/migrations/` with the next available number.
- Real-fixture acceptance is mandatory (per project CLAUDE.md): two real FactSet transcripts must produce the new-shape topics before the epic can close.

---

## 10. Open Questions

| # | Question | Owner | Deadline | Answer |
|---|---|---|---|---|
| **Q1** | Drop strategy for old columns (`decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, `owner`) — DROP at migration time, or stop writing and DROP in a follow-up cleanup commit? | Louis | Architecture step | _open_ |
| **Q2** | `TopicEditor.tsx` and `TopicEvidenceDrawer.tsx` currently read the old fields — collapse into the new flat table component (delete drawer entirely) or refactor drawer to consume the new schema? | Louis | Architecture step | _open_ |
| **Q3** | Confirmation dialog text/style for "Delete topic" — match existing app dialog pattern or new style? | Louis | Build step | _open_ |
| **Q4** | When user deletes the last remaining task in a topic, prompt to delete the topic, or auto-delete? | Louis | Build step | _open_ |

---

## 📝 Amendments Log
*Empty — initial draft.*

---

## 📤 Outputs for 3-ARCHITECTURE.md

- **Tech Stack Hint** → unchanged from `prd.md`
- **Functional Requirements** → component breakdown: prompt module, schema validator, topic service edit endpoints, frontend table component, evidence popover
- **Non-Functional Requirements** → performance budget (NFR-01), observability (NFR-04)
- **Data Requirements** → schema migration design (which columns added, which dropped, when)
- **Interfaces & Integrations** → none new
- **Error Handling Policy** → rejection-on-extract pattern; concurrent-edit policy
- **Constraints** → forward-only migration, regression test mandate
- **User Stories** → US-01..US-09 drive the component-level architecture diagram

---

*→ Once locked, proceed to `3-ARCHITECTURE.md`*
