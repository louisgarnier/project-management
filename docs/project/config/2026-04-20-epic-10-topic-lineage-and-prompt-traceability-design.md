# EPIC-10: Topic Lineage + Full-Stage Traceability + Prompt Quality

> **Goal:** Guarantee full topic lineage traceability across any number of calls (1, 3, 10, 20+), surface evidence at EVERY Kanban stage (Call Topics, Project Matching, Project Updates, Topics Timeline), and ensure every LLM prompt in the pipeline sees the complete historical evidence it needs to produce high-quality output — not just the current call's snapshot.

**Architecture:** Extends Epic 9's M:N merge + verification foundation. Introduces a single lineage helper (`get_topic_lineage`) that walks `merged_into_topic_id` recursively to collect every ancestor topic's `topic_updates`. This helper becomes the canonical source of per-topic history for every merge prompt, verification prompt, artifact prompt, and the new evidence API that powers the UI. No data duplication — archived ancestors remain archived; the helper stitches their history together on read. A single reusable **full-overlay evidence drawer** component surfaces the underlying data at every stage of the Kanban — Call Topics, Project Matching, Project Updates, and Topics Timeline — with stage-appropriate layouts (single-panel for Call Topics, side-by-side for Project Matching, full lineage for Project Updates + Timeline). Distinguishes merge-result topics from fresh topics in the timeline. Audits and fixes every prompt's access to historical context.

**Tech Stack:** Python/FastAPI (backend), Next.js/React (frontend), Supabase (Postgres), existing LLM service.

---

## 1. Problem Statement

Today, as the project accumulates calls, topic evidence fragments and prompts lose visibility into the full history:

1. **M:N merge blindness.** When topics A and B are merged into C in Call 2, Call 1's `topic_updates` rows live on the archived topics A and B. A Call-3 merge on C calls `_load_transcript_excerpts(C)` — which only sees Call 2 + Call 3 rows. Call 1's verbatim transcript excerpt is invisible. Every subsequent merge loses depth of history.
2. **No evidence UI.** The raw `transcript_excerpt`, per-call `summary`, `follow_up_items`, and `decisions` are stored in `topic_updates` but never surfaced in the frontend. The user cannot verify what grounded the merge.
3. **Merge-result topics look new.** A topic that was created by merging A+B in Call 2 appears as "+ new" in the Topics Timeline — indistinguishable from a topic that was truly first-raised in Call 2. The user loses the merge context.
4. **Prompt context inconsistency across call count.** The six LLM prompts in the pipeline each assemble their own context. As calls grow from 1 to 10, each prompt's view of history stays narrow: the extraction prompt doesn't see existing project vocabulary, the match prompt matches on summary only, the merge-verification prompt only sees the current transcript (not ancestor transcripts), artifacts may not see per-call evolution.
5. **Raw per-call extract invisible.** The pre-merge extract from `calls.pending_topics` is retained but never surfaced alongside the merged state, so the user can't see what Call N originally said in isolation.
6. **Match group audit trail hidden.** `topic_match_groups` is kept forever but never shown in the UI after merge — the record of "in Call 2, we grouped A+B+callTopicX together" is lost to the user.

The result: merge quality degrades with call count, verification is shallow, and the user cannot audit any of it.

---

## 2. Goals

1. Every merge prompt, at every call, sees every ancestor topic's transcript excerpt and per-call history — M:N merges no longer cause blindness.
2. A visual evidence panel exposes the complete per-call trail for any topic: transcript excerpts, merged summaries, follow-ups, decisions, match groups, raw pre-merge extracts.
3. Merge-result topics are visually distinct from fresh topics in the Timeline.
4. Every LLM prompt in the pipeline is audited; each has access to the historical context it needs; each fix is either implemented or explicitly deferred with rationale.
5. The same lineage helper powers backend prompts and frontend display — single source of truth.

---

## 3. Non-Goals (explicit deferrals)

- **Per-item follow-up lifecycle** (open/resolved/superseded per item). Current UNION behavior retained.
- **Token-budget compression for very long lineages** (20+ calls). Monitor; revisit only if we hit real LLM context limits.
- **Backfilling `transcript_excerpt` on pre-migration `topic_updates`.** Heals organically as new calls come in.
- **Un-merge soft-delete.** Current hard-delete on rollback retained.
- **Raw pre-merge summary on `topic_updates`.** The raw extract stays recoverable via `calls.pending_topics`; no new column.
- **Manual topic merge UI for non-adjacent calls.** M:N merges only happen during the active call's project matching stage.

---

## 4. Architecture

### 4.1 Single Lineage Helper (Backend Foundation)

**`backend/services/topic_lineage.py` (new module)**

```python
def get_topic_lineage(topic_id: str, db) -> list[dict]:
    """
    Return every ancestor topic row (including the input topic) reachable by
    walking merged_into_topic_id backwards. Each entry: {id, name, archived,
    merged_into_topic_id}. Order: current topic first, then immediate sources,
    then their sources, etc.
    """

def get_lineage_topic_updates(topic_id: str, db) -> list[dict]:
    """
    Return all topic_update rows for a topic and every ancestor via lineage.
    Each row is enriched with source_topic_id (which archived topic it came
    from) and source_topic_name. Ordered by created_at (oldest first).
    """

def get_lineage_match_groups(topic_id: str, db) -> list[dict]:
    """
    Return topic_match_group rows whose project_topic_ids contains this topic
    or any ancestor. For audit-trail display.
    """
```

Consumers: `_load_transcript_excerpts`, `_get_previous_topics` (if relevant), merge-verification prompt, not-discussed-verification prompt, artifact generation (project scope), and the new evidence API.

### 4.2 Evidence API

**`GET /api/topics/{topic_id}/evidence`**

Returns an ancestor-aware, chronological per-call evidence array.

```typescript
type TopicEvidence = {
  topic_id: string;
  topic_name: string;
  lineage: Array<{
    topic_id: string;
    name: string;
    archived: boolean;
    merged_into_topic_id: string | null;
  }>;
  calls: Array<{
    call_id: string;
    call_title: string;
    call_date: string;
    source_topic_id: string;        // which lineage node this evidence came from
    source_topic_name: string;
    transcript_excerpt: string | null;
    merged_summary: string;         // post-merge state after this call
    follow_up_items: string[];
    decisions: string[];
    status: "open" | "in_progress" | "resolved";
    raw_extract: {                  // from calls.pending_topics if present
      summary: string;
      follow_up_items: string[];
      decisions: string[];
    } | null;
    match_group: {                  // from topic_match_groups for this call
      project_topic_ids: string[];
      call_topic_names: string[];
    } | null;
    not_discussed_verification: {   // from calls.verification_cache
      discussed: boolean;
      transcript_excerpt: string | null;
      reasoning: string;
    } | null;
    is_not_discussed: boolean;      // true if no topic_update exists for this call
  }>;
};
```

One entry per call that interacted with the topic or any ancestor, ordered by call date. Silent calls (topic not discussed, not verified) are not included — the consumer can cross-reference call list to render gaps.

### 4.3 Frontend: Topic Evidence Drawer (full-overlay, multi-stage)

**New component: `frontend/src/components/TopicEvidenceDrawer.tsx`**

Approved via mockup (2026-04-20): **full-overlay drawer** — opens as a modal-style overlay that dims the underlying Kanban stage and fills the workspace. Close returns to the stage exactly where the user was. This pattern applies at every mount point; the internal layout varies per stage.

Props:
```typescript
type EvidenceDrawerProps = {
  open: boolean;
  onClose: () => void;
  mode: "call_topic" | "matching" | "lineage";
  // call_topic mode: pending_topic data
  pendingTopic?: { name: string; summary: string; follow_up_items: string[]; decisions: string[]; transcript_excerpt: string | null };
  // matching mode: existing topic lineage on left, current call extraction on right
  matching?: { existingTopicId: string | null; pendingTopicName: string | null; kind: "followed_up" | "new" | "not_discussed" };
  // lineage mode: full ancestor-aware trail for any topic
  topicId?: string;
};
```

**Stage-specific content layouts:**

- **`mode="call_topic"`** (Call Topics stage) — single panel showing the extracted topic's `transcript_excerpt`, summary, follow-ups, decisions. Data source: `calls.pending_topics`.
- **`mode="matching"`** (Project Matching stage) — two-column layout:
  - Left: existing topic's full lineage evidence (reuses `mode="lineage"` content for `existingTopicId`)
  - Right: current call's extraction for `pendingTopicName` (pending_topic data)
  - For `kind="new"`: left shows empty state "No existing project topic matches"
  - For `kind="not_discussed"`: right shows empty state "Not extracted from this call"
  - Footer strip explains the classification ("Matched because same subject across N calls" / "Marked new because no project topic matches the subject" / "Not discussed because LLM found no call topic on this subject")
- **`mode="lineage"`** (Project Updates stage + Topics Timeline) — rich color-coded per-call chronology:
  - Header: topic name + lineage chip ("Merged from: Topic A, Topic B" if `lineage.length > 1`)
  - One card per `calls[]` entry, color-coded by call index (8-color pastel palette cycled)
  - Card header: call title · call date · provenance badge if `source_topic_id !== topic_id` ("from archived topic: {name}")
  - Card body (always visible): transcript excerpt (verbatim, italic), merged summary ("After this call:"), follow-ups, decisions, status badge
  - Card expandable sections (collapsed by default): raw pre-merge extract, match group, not-discussed verification details

**Mount points:**
1. **Call Topics stage** — click any extracted topic card → drawer opens in `mode="call_topic"`
2. **Project Matching stage** — "Show evidence" link on each row (matched / new / not-discussed) → drawer opens in `mode="matching"`
3. **Project Updates stage** — "View evidence" link on each updated topic → drawer opens in `mode="lineage"` (full ancestor trail, richest view — this is where the user validates "did the merge preserve everything?")
4. **Topics Timeline** — click any timeline cell → drawer opens in `mode="lineage"` for that topic

### 4.4 Merge-Result Labeling

Timeline cell rendering change in `frontend/src/components/TopicsTimeline.tsx`:

```typescript
// existing: cell.type === "new" → render "+ new" in green
// new: if cell.type === "new" AND topic.has_sources → render "+ new (merged)" in purple
//     tooltip: "Merged from: Topic A, Topic B"
```

Requires API to expose `has_sources: boolean` + `source_names: string[]` on timeline topics. Cheap to compute — single query `SELECT id, name FROM topics WHERE merged_into_topic_id = $topic_id`.

### 4.5 Prompt Audit Deliverable

Phase 2 produces `docs/project/config/epic-10-prompts-audit.md` with one section per prompt:

| Prompt | Location | Current inputs | Call-count dependency | Blindness | Recommended fix |
|---|---|---|---|---|---|
| Call Topics Extraction | `topics_service.py::extract_call_topics` | | | | |
| Project Topics Merge (auto-match) | `topics_service.py::aggregate_topics` | | | | |
| Per-topic Merge (CRITICAL RULES) | `topics_service.py::save_matches` inline | | | | |
| Merge Verification | `topics_service.py::_verify_merged_topics` | | | | |
| Not-Discussed Verification | `topics_service.py::verify_not_discussed_topics` | | | | |
| Artifacts | `artifacts_service.py` | | | | |

For each, the doc captures: exact context assembly code path, what the LLM sees, what exists in the DB but is withheld, token-budget observation, recommended fix. The audit is the input to Phase 5's implementation.

### 4.6 Prompt Fixes (Phase 5)

Expected changes (subject to audit confirmation):

- **Extraction**: pass existing project topic names (not full data) as vocabulary hints so new call topics align with prior naming.
- **Match (auto)**: include historical `transcript_excerpt` per existing topic, not just summary, so semantic matches are stronger.
- **Per-topic merge**: already fixed by Phase 1 lineage helper — prompt now sees archived ancestors' excerpts.
- **Merge verification**: include transcripts (or excerpts) from every source call in the lineage, not just the current call, so the verifier can confirm older commitments survived.
- **Not-discussed verification**: include prior call excerpts for this topic so the verifier can distinguish "stale" from "just not-discussed-this-call".
- **Artifacts (project scope)**: pass full `topic_updates` history (via lineage helper) so project-scope artifacts can narrate evolution, not just current state.

Each fix is a discrete task in Story 10.6 and only shipped if the audit confirms it is valuable and fits the token budget.

---

## 5. Data Model

**No new columns.** Epic 10 is purely read-layer and prompt-layer work. All data already exists:

- `topics.merged_into_topic_id` (Epic 9) — lineage chain traversed by helper
- `topic_updates.transcript_excerpt` (Epic 9) — verbatim source evidence
- `calls.pending_topics` (Epic 7) — raw pre-merge extracts
- `topic_match_groups` (Epic 9) — match decisions kept forever
- `calls.verification_cache` (Epic 9) — not-discussed verification results

**No migration.** Epic 10 ships without schema changes.

---

## 6. Phased Delivery

### Phase 1 — Lineage helper + merge-prompt fix (Story 10.1)
**Outcome:** Every merge at every call sees every ancestor's transcript_excerpt and history. Quality win, zero UI.

- New module `backend/services/topic_lineage.py` with `get_topic_lineage`, `get_lineage_topic_updates`, `get_lineage_match_groups`
- Update `_load_transcript_excerpts` in `topics_service.py` to use `get_lineage_topic_updates`
- Unit tests: 1:1 chain, 3-call linear, M:N fan-in, grand-merge chain (M:N then 1:1 then M:N again)
- Regression: existing merges without lineage still produce identical output

### Phase 2 — Prompt audit doc (Story 10.2)
**Outcome:** One-document overview of every prompt's context assembly, blindnesses, and recommended fixes. No code.

- Create `docs/project/config/epic-10-prompts-audit.md` with the 6-prompt table populated
- For each prompt, include exact code-line references, input assembly, and a concrete recommendation
- Token-budget envelope per prompt at Call 1, 5, 10, 20
- Deliverable committed before Phase 3 starts

### Phase 3 — Evidence API + lineage drawer (Stories 10.3, 10.4)
**Outcome:** User can click any topic on Project Updates or Timeline and see the complete per-call evidence trail, color-coded, ancestor-aware.

- Story 10.3: `GET /api/topics/{id}/evidence` endpoint powered by lineage helper
- Story 10.4: `TopicEvidenceDrawer` component in `mode="lineage"` + mount on Project Updates stage + mount on Timeline cell-click. Full-overlay drawer (approved 2026-04-20 via mockup).
- Color palette: 8 distinct colors cycled by call index, stable per session
- Expandable raw extract / match group / verification sections per card
- Lineage chip at top if topic was merged

### Phase 4 — Merge-result labeling (Story 10.5)
**Outcome:** Timeline cells on merge-result topics are visually distinct ("+ new (merged)", purple, tooltip with source names).

- Backend: timeline endpoint returns `has_sources` and `source_names[]` on each topic
- Frontend: cell renderer in `TopicsTimeline.tsx` branches on `has_sources`
- Evidence drawer header also shows "Merged from: …"

### Phase 5 — Stage-level evidence surfacing (Stories 10.7, 10.8)
**Outcome:** Same full-overlay drawer (different mode) surfaces underlying data at the Call Topics and Project Matching stages, completing the Kanban-wide traceability story.

- Story 10.7: `TopicEvidenceDrawer` in `mode="call_topic"` — click any extracted call topic → drawer shows pending_topic data (transcript_excerpt + summary + follow-ups + decisions). No new backend work; uses existing `pending_topics`.
- Story 10.8: `TopicEvidenceDrawer` in `mode="matching"` — click "Show evidence" on any match row (followed-up / new / not-discussed) → drawer shows left = existing topic lineage, right = current call extraction. Backend: extend matches response to embed pending_topic data for right pane (no new endpoint).
- Footer strip on `mode="matching"` explains classification based on the data shown (not persisted LLM reasoning).

### Phase 6 — Prompt fixes from audit (Story 10.6)
**Outcome:** Each prompt's recommended fix from Phase 2 is implemented or explicitly deferred with rationale.

- One commit per prompt fix
- Each fix preceded by a test demonstrating the blindness (e.g., Call-3 merge-verify loses Call-1 commitment when not given ancestor transcript)
- Token-budget check after each fix
- Update prompts audit doc to mark each fix as "implemented" or "deferred + reason"

---

## 7. Dependencies

- **Epic 9 complete** ✅ — provides M:N schema, transcript_excerpt, verification cache
- **Epic 7 complete** ✅ — provides `pending_topics` retention
- Epic 10 phases are sequential: Phase 1 gates 3 and 5; Phase 2 gates 5.

---

## 8. Success Criteria

1. **Merge depth test:** A merge at Call 10 that involves a topic first raised in Call 1 and M:N-merged in Call 3 produces a prompt that contains Call 1's `transcript_excerpt`. Verified with a dedicated test.
2. **Evidence completeness test:** The evidence panel for any topic displays one card per call that contributed evidence (including archived-ancestor calls).
3. **Merge-result visibility test:** A timeline cell for a merge-result topic shows "+ new (merged)" in a distinct color; hover reveals source topic names.
4. **Audit deliverable:** `epic-10-prompts-audit.md` exists and references every prompt by file/line; each row has a concrete recommendation.
5. **Prompt-fix coverage:** Each row in the audit is resolved (implemented or deferred with rationale) in Story 10.6.
6. **No regressions:** Existing 1:1 merge flow, single-call extraction, and Timeline rendering pass existing tests unchanged.

---

## 9. Open Questions (resolve during implementation)

- Should the evidence panel be a side drawer (non-modal, keeps context) or a modal? Default: side drawer, user can toggle.
- For the lineage chip, how deep do we render the chain? Default: flat list of immediate sources; show "…and N earlier" if chain is >3 deep.
- Token-budget threshold per prompt before we start compressing old excerpts? Decide during Phase 2 audit.

---

## 10. Out of Scope (reiterated)

- Per-item follow-up lifecycle tracking
- Un-merge soft-delete
- Manual cross-call topic merge UI
- transcript_excerpt backfill
- Token compression strategies (deferred until measured need)
