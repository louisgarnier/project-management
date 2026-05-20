# Brainstorm — EPIC-15 Phase 2: Artifacts Rebuild + xlsx Tracker Export

**Status:** `[x] GO — Proceed to PRD`
**Date:** 2026-05-18
**Branch:** `epic-15-call-topics-rebuild`
**Lodestars:**
- xlsx target: `/Users/louisgarnier/Downloads/FactSet_SWIB_RAM_Tracker_v04.xlsx` (5 sheets after dropping Status review)
- v3 mockup: `call-topic-tile-v3.html` (Phase 1) — extended in Phase 2 with `open_questions[]` + `decisions[]` sections per topic
- New mockup needed: Project tracker sub-tab layout (5 sub-views + Export to xlsx button)

---

## One-line goal
Produce a `FactSet_SWIB_RAM_Tracker_v04.xlsx`-shaped export per project that accumulates correctly across calls — and turn the artifacts page into a flexible "Generate artifacts" surface where the user can spin up custom prompts with the right context scope (this call's transcript, all transcripts, this call's topics, all project topics).

## Why now
- Phase 1 reshaped per-call extraction. Phase 2 is what makes the per-call data add up over time into a project-level tracker that's actually shippable to the client.
- The existing 6 free-text artifacts use legacy fields (`decisions[]`, `follow_up_items[]`, `open_questions[]`) that are now empty under EPIC-15. Either they get rewired or they get retired. Phase 2 chose: rewire to context_scope + per-artifact-type scope value, no special "ad-hoc prompt" feature — every artifact type lives in the library and the user adds their own via the existing AddArtifactTypeModal.

---

## Scope — 4 workstreams (locked)

### P2-A — Call-topics extension (foundation)
- Add `open_questions[]` + `decisions[]` to the call_topics extract output, alongside existing `tasks[]`. **Single prompt** (one LLM round-trip), not multiple — the LLM's cross-section dedup judgment is the real win.
- Schema: add `open_questions JSONB` + `decisions JSONB` to `topic_updates` (new migration). Both items in these arrays follow a consistent shape — at minimum `{ text, ... }`; per-item lifecycle metadata locked in P2-C.
- Call_topics prompt v3 in the library: extend the v2 rubric with two new sections (open_questions + decisions), retaining the dual-classify guidance (an action phrased as "investigate" also goes to open_questions).
- UI: render `open_questions[]` and `decisions[]` as new sections per topic in the v3 table layout. Layout design needed (mockup).
- Sweep read paths the same way Phase 1 did — every SELECT against `topic_updates` that fetches per-call data must include the two new columns.

### P2-B — Custom artifacts + 4-value `context_scope` enum
- Promote `context_scope` to a 4-value enum: `this_call_transcript` / `all_call_transcripts` / `this_call_topics` / `all_project_topics`.
- Migrate the 4 LLM artifacts (Executive Summary, Email Summary, Email Follow-up, Next Call Agenda) + the template/hybrid artifacts to their right scope values in the seed.
- Backend generation engine: assemble the LLM context per scope before calling the model.
- `AddArtifactTypeModal` (frontend) gains a context-scope dropdown so user-added artifacts pick their scope. Existing modal flow is otherwise unchanged.
- This is what closes the "open prompt" request — every custom prompt is an artifact type the user adds.

### P2-C — Project tracker state model + accumulator
- Schema: per-task / per-open-question / per-decision lifecycle metadata — `added_in_call_id` (UUID), `closed_in_call_id` (UUID|null), stored on the JSONB element. Set when item is first inserted / when status flips to resolved.
- New table or new fields for per-(`project_topic`, `call`) chronology cell: narrative paragraph + RAG verification note, frozen at commit time.
- `project_updates` stage upgrade: the merge step accumulates this call's data into project-level state — appends tasks/open_questions/decisions, merges key_terms (union), appends evidence, generates a chronology cell, increments silent-call counters (still computed even though we dropped the Status review sheet — used by future stale-topic flagging if added later).
- New "chronology cell" LLM artifact runs per (topic touched this call) at project_updates commit. Frozen on the (topic, call) row. ~10–50 LLM calls per call (cheap on deepseek-v3.2). Plus 1 verification LLM call per chronology cell at the same commit for the RAG note.

### P2-D — xlsx export + Project tracker sub-tab
- New "Project tracker" sub-tab on the Artifacts page (existing Artifacts page becomes 2 sub-tabs: "Generate artifacts" + "Project tracker"). Topics tab on the project board stays — used in parallel for visual comparison until decided otherwise.
- 5 sub-views inside the Project tracker sub-tab (matching the 5 xlsx sheets):
  - **Dashboard** — 1 row per project topic, with current status, importance, created/last-update dates, open follow-ups bulleted, open questions bulleted.
  - **Chronology** — 1 row per topic × 1 column per call date, plus RAG verification note column. Each cell = the chronology narrative from P2-C.
  - **Anchors lifecycle** — 1 row per task / per open_question. Columns: Topic, Type (Follow-up | Open question), Item, Owner, Added in, Status, Closed in.
  - **Decisions log** — 1 row per decision: Topic, Decision text, Decided in (call date).
  - **Key terms registry** — 1 row per topic with comma-list of all accumulated key_terms and count.
- Export to xlsx button at the top of the sub-tab. openpyxl-based renderer; pure-Python, no new dependency. File downloaded by the browser.

**Dropped from v04:** Status review sheet (user decision: redundant with Dashboard).
**Kept but parallel:** existing Topics tab on the project board — for comparison during smoke. Decision to retire/keep deferred to post-Phase-2 evaluation.

---

## Dependency order
```
P2-A (call_topics extension) ──┐
                                ├──→ P2-C (tracker state) ──→ P2-D (xlsx + sub-tab)
P2-B (context_scope enum) ─────┘ (parallel-safe)
```

## Acceptance criteria — at Phase 2 close
1. Real-fixture test (4 FactSet transcripts, smoke-test project `17e2687f-bdd8-43ee-88a7-d2bd79a13925`):
   - Each call extracts `tasks` + `open_questions` + `decisions` populated.
   - After all 4 calls advance through artifacts, project tracker state holds the accumulated data: tasks with lifecycle metadata, open_questions, decisions, per-(topic, call) chronology cells with RAG notes, key_terms unioned.
2. Clicking "Export to xlsx" on the Project tracker sub-tab downloads a file matching v04 shape (5 sheets, same columns, plausible cell content).
3. User can add a custom artifact via AddArtifactTypeModal with any of the 4 context scopes; generation runs with the correct context.
4. Existing 4 LLM artifacts (Executive Summary, Email Summary, Email Follow-up, Next Call Agenda) regenerate cleanly with non-empty content (no empty `decisions[] / follow_up_items[] / open_questions[]` references — they now reference `tasks[]` / `open_questions[]` / `decisions[]` from the new schema).

## Non-goals (LAW — do not implement in Phase 2)
- xlsx round-trip editing (user edits xlsx → re-imports). Read-only export.
- Status review sheet — dropped.
- Auto-close of topics that fall silent for N calls — silent counter is computed but no auto-archive logic.
- Migration of pre-Phase-1 historical data into the new tracker shape. Forward-only.
- Style / charts / pivot tables in the xlsx beyond what v04 shows.
- Project Matching prompt rework — matching stays manual per user direction in Phase 1.

## Open questions for PRD / Architecture
1. **Chronology cell granularity** — does it sit on the existing `topic_updates` row (one per topic per call), or its own new `chronology_cells` table? Lean toward existing row (no new table); a `chronology_narrative TEXT` + `rag_verification_note TEXT` column on `topic_updates`.
2. **Lifecycle metadata storage** — `added_in_call_id` / `closed_in_call_id` on each task/open_question/decision JSONB element (per-item) vs separate event-log table. Lean toward in-JSONB per-item — simpler, matches existing pattern.
3. **xlsx renderer location** — `backend/exporters/xlsx_tracker.py`, single file. openpyxl. Confirm OK.
4. **AddArtifactTypeModal context-scope dropdown labels** — exact UX strings need finalising at mockup time.
