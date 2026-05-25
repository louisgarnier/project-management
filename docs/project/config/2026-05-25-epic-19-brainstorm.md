# EPIC-19 — Task-Level Project Matching + Narrowed 3-Pass Synthesis — Design

**Date:** 2026-05-25
**Author:** brainstorm session (Louis + Claude)
**Status:** Draft — awaiting user review before plan
**Triggered by:** EPIC-18 Task 18 smoke test on project 'a' / call b (2026-05-25). Pass 1 produced semantically-correct merge verdicts at 18-30% confidence due to topic-level sanity-stack compounding. D5 gate triggered. User pivoted from S2.4 P1-RETRIEVAL (the planned fallback) to this task-level reframe.

**Out of scope:**
- Full task-as-first-class-entity migration (initially considered, rejected as over-scope)
- v5 extraction pipeline changes (v5 stays unchanged)
- Retroactive topic split/merge UX beyond what falls out of N:M task matching
- Frontend Brief / Kanban / Topics dashboard overhaul (consumes the same data; minor cosmetic adjustments only)

---

## 1. Why this exists

EPIC-18 shipped a topic-level verification pipeline (Pass 1 / 2 / 3) that produces correct verdicts but low confidence scores because every sanity check compounds a penalty on a fundamentally fuzzy comparison unit (the topic). The smoke test exposed this:

- `S07`, `Meeting logistics` → 18% confidence (sanity_flag = `citations_lack_rare_terms` — topics with common/code-like terms have no rare terms to cite)
- `Risk model architecture and implementation` → 30% (sanity_flag = `insufficient_verdict_citations`)
- S2.2 P1-BIDIRECTIONAL canonical match path never fires in real usage because `topic_match_groups.project_topic_ids` is always empty (project_matching is a passthrough that doesn't carry v5's canonical assignments)

The root cause is the comparison unit. Topics are abstract aggregations; tasks are concrete units of work. **Move the unit of matching from topic to task. Keep everything else in the pipeline that works.**

---

## 2. The meta-pattern (what we learned the hard way)

Walking the build log: EPIC-15 chronology (twice), EPIC-16 verify_new, EPIC-18 sanity-stack tightening — all attempts at automating cross-call reconciliation via LLM produced mediocre quality at non-trivial cost.

**The only thing in this family that worked was v5 extraction** (EPIC-17), because it inverted responsibility: LLM does cognitive work, code does mechanical work.

**EPIC-19 applies the same principle to reconciliation:** user does the identity decisions (which task is which); LLM only verifies (Pass 1: "is this really new?"), checks (Pass 2: "really not discussed?"), and synthesizes (Pass 3: "produce the merged state").

The matching layer that historically tried to use LLM as the source of truth — that part goes back to being user-driven.

---

## 3. Pipeline overview

```
call_topics (v5)  →  project_matching  →  project_updates (3 passes)  →  artifacts  →  done
   [no change]      [reframed task-level]  [narrowed roles]              [no change]
```

### 3.1 `call_topics` — v5 extraction (no change)

v5 produces atomic units → clusters into topics → synthesizes tasks per topic. Each task has: `task_id`, `task` text, `next_step`, `owner`, `status`, `key_terms`, `open_questions`, `decisions`, `citations` (line-numbered).

**The conceptual shift:** the task is the unit of truth. Topics are containers/groupings. This is already how v5 internally works; EPIC-19 just propagates this shift downstream.

### 3.2 `project_matching` — task-level manual binding (REVIVED + REFRAMED)

The old `project_matching` stage (topic-level drag-and-drop) is replaced with a task-level matching UI.

**Input:** v5's output for this call (candidate topics + their candidate tasks) + project's existing topics + their existing tasks (from `project_topic_state` view).

**User actions (per session, manual):**

- Bind one or more candidate tasks to one or more existing tasks (N:M).
  - 1:1 — straight continuation (most common case)
  - N:1 — call B refined N old tasks into 1 (consolidation)
  - 1:N — call B split 1 old task into N sub-tasks
  - N:M — refactored work stream; the user designates which goes where
- Mark a candidate task as "new" (no binding to any existing).
- Mark an existing task as "not touched this call" (no candidate binds to it).
- When a binding crosses topic boundaries (candidate task's v5-topic ≠ existing task's project-topic), the UI surfaces a topic decision: which topic does the merged task live under? Or, if many cross-topic bindings → propose a topic merge.

**Output (persisted):**

- A list of N:M task `match_groups` with bound (candidate, existing) task references
- Per candidate task that wasn't bound: status `new`
- Per existing task that received no bindings: status `not_touched_this_call`
- Three derived topic buckets ready for Pass 1/2/3:
  - **new_topics:** topics from v5 whose tasks were all marked "new"
  - **old_untouched_topics:** existing project topics whose tasks were all marked "not_touched_this_call"
  - **merged_topics:** existing topics that received at least one task binding (or a topic-merge decision)

**No LLM involvement in this stage.** Purely manual. The system can pre-render lexical hints (e.g. exact text matches highlighted) to speed up review, but cannot auto-bind.

### 3.3 `project_updates` Pass 1 — narrowed "verify new" (safety net)

**Scope:** only the `new_topics` bucket from matching.

**Job:** for each candidate topic the user marked as "new" (i.e., none of its tasks bound to existing tasks), verify against past transcripts + the project's existing tasks that no semantically-equivalent task was missed in manual matching.

**LLM input per topic:**
- The candidate topic's tasks (task description, next_step, key_terms, citations from v5 extraction)
- The previous call's project_updates output for the project (accumulated state per topic: existing tasks with their next_step, key_terms, status, evidence trail) — narrowed to top-K topics by mechanical similarity
- Previous calls' transcripts (line-numbered, EPIC-18's pattern) — for verifying whether the candidate's work was ever discussed before

**Output:**
- `verdict ∈ {"confirmed_new", "suggest_merge_with"}`
- For `suggest_merge_with`: target task(s) the LLM thinks the candidate's work continues, with citations
- User has final word: confirm new (LLM was wrong), OR accept LLM's suggestion to merge with the proposed task/group (single or N:M group)

**What disappears vs EPIC-18 Pass 1:**
- No more rarity check + sanity penalty stack (the LLM's job is narrower; confidence reflects actual match quality, not penalty compounding)
- No `verify_canonical_match` / S2.2 path (the bucket distinction at matching time replaces it)
- No `extraction_grounded` field
- No multi-tier verdict states (`wrong_canonical_*`)

### 3.4 `project_updates` Pass 2 — narrowed "verify not discussed" (safety net)

**Scope:** only the `old_untouched_topics` bucket from matching.

**Job:** for each existing topic whose tasks the user marked as "not touched this call," verify against the CURRENT call's transcript only that no tasks were actually mentioned/updated.

**LLM input per topic:**
- The existing topic's tasks from the previous call's project_updates output (anchor: task description, next_step, key_terms, last status)
- Current call's transcript (line-numbered) — the ONLY transcript Pass 2 needs to scan

**Output:**
- `verdict ∈ {"confirmed_not_discussed", "suggest_discussed_at"}`
- For `suggest_discussed_at`: line range citation pointing to the transcript passage that mentions a task from this topic
- User has final word: confirm not discussed, OR re-bind the candidate task(s) to the existing tasks (loop back to matching; topic moves from `old_untouched_topics` to `merged_topics` for Pass 3)

**What disappears vs EPIC-18 Pass 2:**
- Free-form quote citation (replaced with line-number per EPIC-18's ADR-004 pattern, but now applied to Pass 2)

### 3.5 `project_updates` Pass 3 — task-merge synthesis (REWRITTEN)

**Scope:** every topic that lands in the `merged_topics` bucket by the time Pass 3 runs. This includes:
- Topics initially placed in `merged_topics` at project_matching (the manual stage)
- Topics that moved from `new_topics` → `merged_topics` because the user accepted Pass 1's "suggest merge with X" suggestion
- Topics that moved from `old_untouched_topics` → `merged_topics` because the user accepted Pass 2's "actually discussed at line X" suggestion

Pass 3 runs LAST in `project_updates`, after Pass 1 and Pass 2 have potentially reshuffled buckets via user overrides. By the time Pass 3 starts, the bucket assignments are final.

**Job:** for each merged topic, produce an up-to-date snapshot of the topic that combines:
- Previously accumulated state (the topic's last `topic_updates` row from the prior call — i.e., the previous call's project_updates OUTPUT for this topic)
- New tasks bound to this topic in the current call (via match_groups + Pass 1/2 user overrides)
- Resolved next_step / status / summary / decisions / open_questions per task, using the latest evidence

**This is NOT re-extraction.** It's synthesis from already-confirmed bindings.

**LLM input per topic:**
- Previous call's `topic_updates` row for this topic (the accumulated chronological state with all prior tasks + history)
- Newly-bound candidate tasks from this call (with their v5 citations)
- All previous transcripts (line-numbered) — for citation grounding when older history is referenced
- Current transcript (line-numbered) — for citation grounding on new bindings

**Output (one new `topic_updates` row per merged topic):**
- Per task: updated `task`, `next_step`, `status`, `key_terms`, `open_questions`, `decisions`, `primary_citation`
- Topic-level: summary, status rollup, importance, sentiment
- Evidence trail: chronological history of citations across calls for this topic

**What disappears vs EPIC-18 Pass 3:**
- Full re-extraction of tasks from raw transcripts (heavy LLM work, often produced spurious tasks)
- Open-ended task discovery (Pass 3 was treating new candidate tasks as a re-extraction; now Pass 3 only synthesizes from the matching + Pass 1/2 decisions)

### 3.6 `artifacts` — no change

Existing artifact generation runs against the post-Pass-3 project state.

---

## 4. Data model

### 4.1 What stays as-is

- `topics` table (project_id, name, calls_open, archived, first_raised_call_id)
- `topic_updates` table (topic_id, summary, status, tasks JSONB, open_questions JSONB, decisions JSONB, evidence, key_terms, chronology_narrative, rag_verification_note, created_at) — this remains the chronological accumulator per topic
- `project_topic_state` view (EPIC-18 ADR-003) — keeps working
- v5's tables (`calls.call_topics_v5_payload`, `topic_registry`) — no change

### 4.2 What changes — `topic_match_groups` table

Currently the table holds `(call_id, call_topic_names[], project_topic_ids[])` — topic-level matching.

**EPIC-19 schema change (migration 035):**

```sql
ALTER TABLE topic_match_groups
  ADD COLUMN call_task_refs JSONB,    -- [{call_topic_name, task_id_in_pending}]
  ADD COLUMN project_task_refs JSONB; -- [{project_topic_id, task_id_in_latest_update}]
-- existing call_topic_names + project_topic_ids columns retained for back-compat reads,
-- populated with derived topic names/ids from the task refs
```

Each row = one N:M match group. A group with multiple `call_task_refs` and one `project_task_refs` is an N:1 consolidation. Etc. Empty `project_task_refs` on a group with `call_task_refs` = "new tasks (no binding)". Empty `call_task_refs` on a group with `project_task_refs` = "not touched this call."

### 4.3 What stays consistent

Pass 3's output remains a `topic_updates` row per merged topic. Schema unchanged. The synthesis just produces it differently (from match group bindings instead of from raw re-extraction).

---

## 5. Frontend

### 5.1 What's deleted

- The topic-level `project_matching` UI (drag candidate topic → existing topic). Replaced.

### 5.2 What's reworked

**Task-level matching UI** — replaces the topic-level matching page:

- Left pane: project's existing topics + tasks (grouped by topic, expandable)
- Right pane: this call's candidate topics + tasks
- Center: match groups being built (N:M bindings shown as connections)
- Per candidate task: actions: "Bind to existing task →", "Mark new"
- Per existing task: actions: "Mark not touched this call"
- Cross-topic-binding modal: when user binds candidate task A (v5-topic X) to existing task B (project-topic Y) and X≠Y → prompt: "Which topic should the merged task live under? X, Y, or new merged topic?"
- Bulk hint: pre-highlight exact-text matches between candidate task text and existing task text (mechanical, no LLM)
- "Done" button → persists match groups → advances to project_updates

### 5.3 What's preserved from EPIC-18

- Pass 1 review UI: existing `ProjectUpdatesStage.tsx` for new_topics — narrowed to handle `verify_new`-style output only (no canonical_match verdicts; no `wrong_canonical_*` labels)
- The "Override: merge instead" button pattern (user final word)
- Auto-accept eligibility flag from EPIC-18 STREAM 4 still applies for high-confidence `confirmed_new`

### 5.4 What's new

- Pass 3 synthesis review screen (or inline display): show the merged topic update with explicit task-level provenance ("this task's status changed from open→in_progress in call N because [citation]")

---

## 6. What deletes vs. preserves vs. builds

### Deletes (code removed)

- `backend/prompts/verify_new_topic.py::VERIFY_CANONICAL_MATCH_PROMPT` (S2.2 P1-BIDIRECTIONAL — never triggered)
- `backend/services/topic_verification.py::run_verify_canonical_match` (same)
- The rarity check (`check_citation_rarity`)
- The sanity flag penalty stack in `compute_confidence`
- The full re-extraction prompt body in `backend/prompts/extract_topic_updates.py` (replaced with synthesis prompt)
- Frontend rendering of `wrong_canonical_*` verdict labels

### Preserves (still pays off from EPIC-18)

- `project_topic_state` view (ADR-003)
- Line-number citation pattern (ADR-004) — extended to Pass 2 + Pass 3 in this epic
- v5 structured registry (V5-CORE) — v5 still uses it for clustering
- `projects.context` wiring (V5-CONTEXT)
- Pass 1 fixtures (adapt to the narrowed Pass 1 contract)
- Verification asymmetry UX (auto-accept high-confidence)
- Migration script pattern

### Builds

- Migration 035: `topic_match_groups` schema extension for task-level refs
- `backend/services/task_match_persistence.py` (small service to save/load the new schema)
- New Pass 3 synthesis prompt body + orchestration
- Pass 2 prompt migration to line-number citations
- Frontend task-level matching UI component
- Pass 3 synthesis review screen
- Migration script: `repopulate_match_groups_for_task_level.py` for historical projects

---

## 7. Work order + phases

```
Phase 1 — Backend foundation (~3 days)
  Migration 035 (topic_match_groups schema extension)
  task_match_persistence service
  save_match_groups endpoint accepts task-level refs

Phase 2 — Pass 1 narrowing (~1 day)
  Strip canonical_match path, rarity check, sanity stack
  Adapt fixtures
  Verify tests green

Phase 3 — Pass 2 line-number migration (~1 day)
  Adopt EPIC-18's line-number citation pattern in Pass 2 prompt + orchestration

Phase 4 — Pass 3 synthesis rewrite (~2 days)
  New synthesis prompt body
  New run_synthesize_merged_topic function
  Inputs: bound tasks + previous topic_updates + transcripts
  Output: one new topic_updates row per merged topic

Phase 5 — Frontend task-level matching UI (~3 days)
  New task-matching component
  N:M binding state + cross-topic decision modal
  Replace topic-level matching page in router

Phase 6 — Migration + smoke (~1 day)
  Backfill script (existing topic-level match_groups → task-level)
  Smoke test on project a + project b
  Update docs

Total: ~11 days
```

---

## 8. Risks + kill switches

| Risk | Mitigation |
|---|---|
| Manual task matching is too tedious — user finds it slow | Phase 5 must include keyboard shortcuts + bulk-bind by exact-text match (single-click). If still slow, can layer LLM pre-suggestion in v2 (out of scope for v1) |
| Pass 3 synthesis prompt produces low-quality summaries when many tasks bound across many calls | Test on project a (4 calls, accumulated state) before locking the prompt. Iterate. |
| Pass 1's narrowed safety-net misses real misclassifications | Run against the same project a/b real-data smoke as EPIC-18; compare verdicts. If parity, ship. |
| Historical topic-level match_groups don't translate cleanly to task-level | Migration script writes one task_match_group per old topic_match_group, mapping all tasks of source topic → all tasks of target topic (bulk N:M). Smoke per project. |
| User binds a candidate task to multiple existing tasks (genuinely N:M case) and the UX feels overloaded | Phase 5 design: match groups are first-class entities in the UI; selecting a group shows all bound tasks side by side |

**Kill switch:** if Phase 5 (frontend matching UI) lands but is too painful in real use (project a + b retest), we revert to topic-level matching for the manual stage and keep the narrowed Pass 1/2/3 + line-number citations. That alone would still be net-positive over EPIC-18 baseline.

---

## 9. Acceptance criteria

1. **Project b same-transcript test:** vast majority of candidate tasks should bind via 1:1 exact text match (v5 at temp=0 on identical transcripts → highly deterministic task text). Pass 1 fires on 0-1 candidates. (Assumption to validate in Phase 6 smoke — if exact match rate is much lower than expected, the deterministic-LLM assumption needs revisiting.)
2. **Project a real-data smoke:** user can complete task-level matching for call b in <10 minutes. Pass 1 surfaces 0-2 "you might have missed this merge" suggestions, not 7. Pass 3 produces coherent merged updates with citations.
3. **Confidence numbers:** Pass 1's `confirmed_new` verdicts land at ≥80% confidence (vs 18-30% today) because the rarity + sanity stack is gone.
4. **Migration:** historical projects (RAM, RAM2, etc.) continue to render in Kanban + Topics dashboard after migration. No data loss.
5. **No regressions:** `pytest backend/tests/` + `npx tsc --noEmit` + `npm run lint` clean.

---

## 10. What this design does NOT promise

- **Pass 1 / Pass 2 still have LLM dependency.** They're verification, not the primary matcher. Failures are local and advisory.
- **Pass 3 is LLM-dependent for synthesis.** It's the heaviest LLM work in the pipeline. We're making it narrower than EPIC-18's full re-extraction, but it's still LLM-driven and will produce occasional bad summaries.
- **Manual matching has user cost.** EPIC-19 trades LLM-uncertainty for user-time. For one PMO at human scale this is the right trade. At larger scale it would need re-evaluation.
- **No retroactive topic split/merge UX** beyond the cross-topic-binding modal at matching time. If three calls in, the user realizes "topic X should have been split," that's a separate manual operation not addressed here.
- **`projects.context` priming and v5 structured registry** carry over but are not re-tuned. If v5 produces poor clusters, EPIC-19 doesn't fix that (it just means the user has more "new task" binding decisions to make).

---

## 11. Open questions before plan

- **Q1:** Should Pass 1 + Pass 2 run in parallel (different topic buckets, no overlap) or sequentially? — *Recommend parallel; they touch independent buckets.*
- **Q2:** Pass 3 — one LLM call per merged topic, or batch all merged topics into one call? — *Recommend per-topic for narrower context; parallelizable for latency.*
- **Q3:** Cross-topic binding decisions: persist in `topic_match_groups` as a special row type, or as a topic rename/merge action separately? — *Resolve in plan; lean toward special row type.*
- **Q4:** Pass 3 synthesis prompt: receive `topic_updates` history as text or as structured JSON? — *Recommend structured JSON; LLM gets clearer task identity that way.*
- **Q5:** Frontend matching UI: keyboard-driven (j/k/space) or fully click? — *Lean toward keyboard for speed; spec a "matching power user" interaction model in plan.*
