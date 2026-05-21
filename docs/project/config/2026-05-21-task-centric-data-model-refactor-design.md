# Design — Task-Centric Data Model Refactor

**Date:** 2026-05-21
**Status:** Design (pending user review)
**Scope:** refactor the topic data model so that key_terms, open_questions, decisions, and evidence (citations) live at the TASK level rather than the topic level. The topic becomes a thin container; the task is the atomic unit of work + supporting context.

---

## 1. Motivation

Today's data model:

```
topic = {
  name, importance,
  key_terms: [...]        ← topic-level
  open_questions: [...]   ← topic-level
  decisions: [...]        ← topic-level
  evidence: [...]         ← topic-level
  tasks: [
    {task, next_step, status, owner, citations: [...]}  ← only these are per-task
  ]
}
```

User's mental model: a **task** is a discrete commitment with its own supporting context (what was said, what's still open, what was decided about it, who owns it). The topic is just a way to group related tasks for navigation.

The mismatch creates real workflow problems:
- "Move task X from Topic A to Topic B" leaves OQ/decisions/key_terms (the supporting context for X) stranded on A.
- LLM extraction produces topic-level OQ/decisions even when those items clearly belong to a specific task.
- Pass ① duplicate detection uses topic-level key_terms, which average out across tasks of different specificity.
- Audit trail per task is fragmented (citations are per-task, but the OQ that justifies a task lives at topic level).

**Goal:** align the data model with the workflow. Tasks own their context.

## 2. New data model

```
topic = {
  name: string,
  importance: "high" | "medium" | "low",
  tasks: [
    {
      task_id: string,
      task: string,
      next_step: string,
      status: TopicStatus,
      owner: string,
      key_terms: string[],            ← now per-task
      open_questions: [{...}],         ← now per-task
      decisions: [{...}],              ← now per-task
      citations: [{speaker, quote, lines}],  ← already per-task as of recent change
      added_in_call_id?: string,
      closed_in_call_id?: string,
    }
  ],
}
```

Topic-level fields removed: `key_terms`, `open_questions`, `decisions`, `evidence` (legacy `topic.evidence` kept for backward compat reading only — not populated by new extractions).

Topic keeps: `name`, `importance`, `summary` (derived view), `tasks[]`.

## 3. Non-goals

- We are NOT eliminating the concept of topic. Topics still group related tasks for UI organization, Pass ① matching anchor, lineage.
- We are NOT changing call_topics or other workflow stages structurally — only the data shape extracted/persisted at call_topics + read downstream.
- We are NOT migrating existing topic_updates rows. Backward-compat reads pull legacy topic-level fields when per-task fields are absent.

## 4. Architecture overview

### Affected layers

| Layer | Change |
|---|---|
| **`backend/prompts/call_topics.py`** | New CALL_TOPICS_V4_PROMPT_BODY. Output schema: task object carries name, next_step, status, owner, key_terms, open_questions, decisions, citations. Topic carries name, importance, tasks[]. |
| **`backend/services/topics_service.py::_validate_topic`** | Validates per-task key_terms (optional, list[str]), per-task open_questions (optional list of dicts), per-task decisions (optional list of dicts), per-task citations (already validated). Topic-level OQ/decisions/key_terms remain accepted for back-compat. |
| **`backend/services/topics_service.py::_persist_topic_update`** | Writes tasks JSONB with per-task richness. topic_updates.open_questions/decisions/key_terms columns still populated (aggregated from tasks) for back-compat reads. |
| **`backend/services/topics_service.py::list_call_topics`** | Returns per-task richness via tasks JSONB. Optionally derives aggregated topic-level views. |
| **`frontend/src/types/index.ts`** | TaskData gains `key_terms?: string[]`, `open_questions?: OpenQuestionData[]`, `decisions?: DecisionData[]`. TopicData keeps existing fields (legacy) but new code reads from tasks. |
| **`frontend/src/components/CallTopicsStage.tsx`** | Each task row renders its own key_terms chips, OQ list, decisions list, citations button. Topic-level cells (first row of topic block) show only name + importance + computed `Σ tasks count, Σ OQ count, Σ decisions count`. |
| **`frontend/src/components/ProjectUpdatesStage.tsx`** | Pass ①/②/③ cards aggregate per-task data when displaying topic-level summary. |
| **`backend/services/topic_verification.py`** (Pass ①) | `effective_token_set` aggregates per-task key_terms when present, else falls back to topic-level. IDF computation operates on aggregated token sets. Scoring uses union of all task-level key_terms + topic name. |
| **`backend/services/topic_verification.py`** (Pass ③) | `_build_extract_updates_prompt` includes the per-task data of existing topics. `run_extract_topic_updates` output schema: same as current but each task explicitly owns its OQ/decisions/key_terms. |

### Data flow

**call_topics extraction (v4 prompt):**
- LLM emits topic with per-task OQ/decisions/key_terms.
- `_validate_topic` accepts the new shape.
- `_persist_topic_update` writes tasks JSONB with embedded per-task fields.
- For backward compat, also aggregates per-task OQ/decisions/key_terms into topic-level columns at write time (a single union pass).

**Reads (any downstream stage):**
- Frontend reads `topic.tasks[i].key_terms` (new) when present, falls back to `topic.key_terms` for legacy rows.
- Same pattern for open_questions, decisions, citations.

### Move-task semantics

When user moves Task X from Topic A to Topic B:
- Task X's full object (task_id, task, next_step, owner, status, key_terms, OQ, decisions, citations, added_in_call_id, closed_in_call_id) moves to B.
- A loses task X from its tasks[].
- Topic-level aggregates on A and B are recomputed at next save.

## 5. Implementation phases (each independently shippable)

### Phase 1 — Foundation (backend extraction + types) ~3h
1. New CALL_TOPICS_V4_PROMPT_BODY with per-task schema. Library entry updated.
2. `_validate_topic` extended: accepts task.key_terms (list[str]), task.open_questions (list[dict]), task.decisions (list[dict]).
3. `_stamp_item_ids` ensures stable IDs across nested per-task arrays (OQ ids, decision ids).
4. `_persist_topic_update` aggregates per-task fields into topic-level columns at write time (back-compat).
5. `TaskData` type gains optional fields. Other TS types unchanged.
6. Backend tests for new validator paths.

### Phase 2 — CallTopicsStage UI ~2h
1. Render per-task key_terms (chips, editable).
2. Render per-task open_questions (mini list, editable, add/delete).
3. Render per-task decisions (mini list, editable, add/delete).
4. Topic-level cells (name + importance) become a thin header showing aggregated counts.
5. Legacy topic-level OQ/decisions still displayed (read-only) for old data; new edits go to per-task.

### Phase 3 — Move task migrates everything ~30min
1. The right-click "Move task to topic" handler already moves the full task object — verify task.key_terms/OQ/decisions/citations all transfer.
2. No additional UI change; only verification + test.

### Phase 4 — Pass ① + ③ adapted ~3h
1. `effective_token_set` reads per-task key_terms (union across tasks of the topic) when present, else topic-level fallback.
2. Pass ① prompt input includes per-task OQ/decisions/key_terms in the existing topics block.
3. Pass ③ output schema: each task in the extracted_snapshot carries its own OQ/decisions/key_terms.
4. Backend tests for the new aggregation logic.

### Phase 5 — Cleanup ~1h
1. Remove topic-level OQ/decisions/key_terms writes from new code paths (back-compat reads stay).
2. Frontend: deprecate legacy topic-level renderers (keep guard for old data).
3. Document the new model in `docs/project/config/codebase.md`.

## 6. Backward compatibility

**Reads:**
- New code reads per-task fields first; falls back to topic-level if absent.
- All existing topic_updates rows continue to work; they just don't have per-task richness until re-extracted.

**Writes:**
- New extractions (call_topics v4) populate per-task fields AND aggregate them to topic-level (back-compat).
- After Phase 5, only per-task fields are written. Legacy topic-level columns remain in schema but become unused.

**No DB migration:**
- topic_updates table schema unchanged.
- tasks JSONB already accommodates any extra fields per task — no ALTER needed.

## 7. Risks + mitigation

| Risk | Mitigation |
|---|---|
| Pass ① accuracy regression — new key_term aggregation could shift scoring | Keep IDF threshold tunable. Test with project A (real data) before merging. |
| LLM v4 prompt produces poorer extractions | A/B compare v3 vs v4 on a known call. Roll back v4 if quality drops. |
| Existing data + new data mixed in same project | Backward-compat reads handle both. Re-extract a call to migrate it forward. |
| UI complexity — per-task OQ/decisions/key_terms is more visual clutter | Use collapsibles. Topic name row stays compact; details expand on click. |
| Move-task breaks Pass ① caches | After move, mark Pass ① cache stale to force re-run. |

## 8. Acceptance criteria

- [ ] After re-extracting a call, `topic_updates.tasks[i]` carries `key_terms`, `open_questions`, `decisions`, `citations`.
- [ ] CallTopicsStage renders these per-task in the table.
- [ ] User can edit per-task key_terms / OQ / decisions inline.
- [ ] Move task right-click migrates all per-task data with the task.
- [ ] Pass ① lexical pre-check uses aggregated per-task key_terms.
- [ ] Pass ③ output schema places OQ/decisions/key_terms inside each task object.
- [ ] Old topic_updates rows (no per-task data) still display via legacy fallback.
- [ ] All existing backend tests pass.
- [ ] At least 5 new tests cover the per-task validator paths.

## 9. Open questions / risks (revisit during implementation)

- **Topic-level aggregations for display**: do we compute on-the-fly in UI, or persist alongside per-task? Decision: compute in UI for simplicity.
- **Tracking tasks** (where the LLM emits a placeholder "Track X" task with no concrete content): do these still get per-task OQ/decisions/key_terms, or are they minimal? Decision: minimal — tracking tasks can have empty arrays.
- **Decision text field** is currently `{text}` only. Per-task decisions may want `{text, status, owner}` for richer tracking. Decision: keep current shape `{text}`, add fields if Pass ③ needs them later.
