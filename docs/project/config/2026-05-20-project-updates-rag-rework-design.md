# Design — Project Updates RAG Rework

**Date:** 2026-05-20
**Status:** Design (pending user review)
**Scope:** rework of the `project_matching → project_updates` transition + the `project_updates` stage itself, replacing auto-LLM merge with user-triggered, citation-grounded verification passes.

---

## 1. Motivation

Today's `project_updates` stage runs two LLM processes automatically:

1. `verify_not_discussed_topics` (background, triggered by `save_match_groups`)
   — sends the FULL transcript to the LLM once per not-discussed topic. Blows the TPM cap on Groq tiers (observed 413 errors on calls with ~14k-token transcripts). Single-purpose check, no audit trail.

2. `run_merge_preview` (background, triggered by arrival on the stage)
   — runs an LLM "merge" of existing topic + call topic data per match group. Sees previously-extracted summaries/tasks/decisions (which may themselves already be hallucinated) and re-synthesises them, compounding drift across calls. Output is not citation-grounded. No mechanism to detect or correct hallucination.

By call 3+ of a project, the "current state" of a topic can be 2-3 layers of LLM reformulation deep, with no link back to what was actually said. The user cannot tell whether an "update" is real or fabricated.

## 2. Goals

- Replace the auto-merge with a **user-driven, citation-grounded** verification flow
- Make transcripts the **single source of truth** for every claim ever surfaced in `project_updates`
- Surface an **auditable evidence trail** for each topic — chronological citations across all the calls it appeared in
- Eliminate the TPM-blowing per-topic full-transcript blast pattern
- Restore deterministic stage transitions: `Save & Continue` on matching becomes a pure DB advance, no LLM work

## 3. Non-goals

- No new RAG infrastructure (embeddings, pgvector, vector stores). Big-context models (Claude Sonnet 4.6 1M tokens) are sufficient for the project scale (single user, 10-50 calls per project).
- No automatic background processing on stage transitions. Every LLM call requires explicit user action.
- No changes to `call_topics`, `project_matching`, `artifacts`, or `done` stages (other than removing the auto-trigger out of matching).
- No re-extraction or modification of historical `topic_updates` rows. New extraction lives in the call N row only; prior rows are immutable.

## 4. Architecture overview

### 4.1 Stage transition changes

```
matching      Save & Continue  →  project_updates    Save & Continue  →  artifacts
─────────                          ───────────────
NO LLM                             NO LLM until user
NO bg task                         clicks ① ② ③
```

### 4.2 New UI layout: `project_updates` becomes 3 sequenced sections

```
┌─ Project Updates — Call N ─────────────────────────────────────────────┐
│                                                                        │
│ ┌─ 1. New topics from this call (k)  ──── [① Verify new] ─────────┐  │
│ │   (cards with raw call-topics extraction)                         │  │
│ └───────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│ ┌─ 2. Old topics not in this call (m)  ── [② Verify not disc.] ────┐  │
│ │   (disabled until ① done)                                         │  │
│ │   (cards showing latest snapshot from N-1 lineage)                │  │
│ └───────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│ ┌─ 3. Merged topics (n)  ────────────── [③ Extract updates] ───────┐  │
│ │   (disabled until ② done)                                         │  │
│ │   (side-by-side: PREVIOUS (N-1 lineage) ║ THIS CALL (raw))        │  │
│ └───────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│   [Save & Continue → Artifacts]  (disabled until ① ② ③ all done)      │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Order of operations (enforced)

1. **① Verify new** — runs first. Can re-classify a "new" topic as "should be merged with existing topic X" → topic migrates from section 1 to section 3.
2. **② Verify not discussed** — runs second. Can re-classify an "old not-in-call" topic as "actually discussed" → topic migrates from section 2 to section 3.
3. **③ Extract updates** — runs last on the FINAL section 3 set (initial merged + ① migrations + ② migrations).

`Save & Continue → Artifacts` is disabled until all three buttons have produced a `done` status.

Re-clicking a button (e.g., after manually editing a topic) re-runs that section and disables downstream buttons until they re-run too.

## 5. The 3 verification passes — specification

### 5.1 Source of truth (invariant)

Every LLM call receives **raw transcripts** as its only ground truth. Previously-extracted topic data (summaries, tasks from earlier `topic_updates`) is used as **anchor only** — i.e., to tell the LLM "this is the topic name + key_terms you're investigating" — never as factual basis.

| Pass | Anchor data | Transcripts in prompt | Output |
|---|---|---|---|
| ① verify_new_topic | new topic's name + key_terms + tasks/OQ/decs (from call_topics extraction) | all calls 1..N transcripts | verdict + citations |
| ② verify_not_discussed | old topic's name + key_terms | call N transcript only | verdict + citation if found |
| ③ extract_topic_updates | merged topic's name + key_terms (anchor only — no summaries, no prior tasks) | all calls 1..N transcripts | complete topic_update snapshot + evidence_trail |

### 5.2 Citation contract

Every claim, field, and verdict produced by any of the 3 passes MUST be supported by at least one citation:

```json
{
  "call_id": "<uuid>",
  "lines": "X-Y",
  "quote": "<verbatim copy-paste from transcript body>"
}
```

- `quote` is verbatim. No paraphrasing, no abbreviation, no ellipsis-replacement.
- Post-process verifies each `quote` appears verbatim in the cited call's `transcript` via `quote in transcript_body` string check.
- If any citation fails verification → 1 retry with explicit failure feedback in prompt → if still fails → topic marked `needs_manual_review`, UI shows red warning instead of green ✓.

### 5.3 Pass ① — `verify_new_topic`

**Purpose:** confirm the topic is genuinely new (not a missed match) AND confirm the call-topic extraction didn't fabricate content.

**Input to LLM:**
- New topic: `{name, key_terms, tasks, OQ, decisions}` (the call_topics output)
- Existing project topics: `[{topic_id, name, key_terms}]` (anchor only, no summaries)
- Transcripts: all calls 1..N bodies

**LLM output (JSON):**
```json
{
  "verdict": "truly_new" | "should_be_merged_with",
  "matched_topic_id": "<uuid>",      // only if verdict == should_be_merged_with
  "extraction_grounded": true/false, // (b) check: are the new topic's tasks/OQ/decs really in call N transcript?
  "ungrounded_items": [...],          // list of tasks/OQ/decs that don't have transcript support
  "citations": [
    {"call_id": "...", "lines": "...", "quote": "..."},
    ...
  ]
}
```

**UI effect:**
- `truly_new` → ✓ on the card, stays in section 1
- `should_be_merged_with: <topic_id>` → card migrates to section 3 (Merged), badge "moved from New", flag `needs_extraction` so user re-runs ③ to extract its updates
- `extraction_grounded: false` → warning badge listing ungrounded items, user can edit/delete them inline before continuing

### 5.4 Pass ② — `verify_not_discussed`

**Purpose:** confirm the topic was truly not discussed in call N (catch missed matches).

**Input to LLM:**
- Topic: `{name, key_terms}` (anchor)
- Transcript: call N only

**LLM output (JSON):**
```json
{
  "verdict": "not_discussed" | "actually_discussed",
  "citation": {...} // only if actually_discussed
}
```

**UI effect:**
- `not_discussed` → ✓ on the card, stays in section 2
- `actually_discussed` → migrates to section 3 (Merged) with the citation already attached. Flagged `needs_extraction`.

### 5.5 Pass ③ — `extract_topic_updates`

**Purpose:** produce a transcript-grounded `topic_update` snapshot for call N, with full evidence trail.

**Input to LLM:**
- Topic: `{name, key_terms}` (anchor only — NO prior summary, NO prior tasks)
- Transcripts: all calls 1..N bodies

**LLM output (JSON):**
```json
{
  "extracted_snapshot": {
    "summary": "...",
    "status": "open|in_progress|resolved",
    "tasks": [
      {"task": "...", "next_step": "...", "owner": "...", "status": "...",
       "primary_citation": {...}, "supporting_citations": [...]}
    ],
    "open_questions": [
      {"text": "...", "owner": "...", "status": "...", "primary_citation": {...}}
    ],
    "decisions": [
      {"text": "...", "primary_citation": {...}, "supporting_citations": [...]}
    ]
  },
  "evidence_trail": [
    {
      "call_id": "...",
      "citation": {...},
      "action_label": "first raised" | "task added" | "decision recorded" | "OQ resolved" | "status change" | "scope expanded" | ...
    },
    ...  // ordered chronologically across all calls
  ]
}
```

**UI effect:**
- ✓ Verified badge with `N changes` count
- Card body shows: SNAPSHOT (top) + EVIDENCE TRAIL (bottom, scrollable)
- Each field in the snapshot has a `[→ Call X cit-Y]` tag that scroll-anchors to the corresponding evidence_trail entry
- User can `Accept`, `Re-extract` (clears + re-runs), or `Edit manually` (manual mode disables auto-overwrite)

## 6. Anti-hallucination mechanisms (defense-in-depth)

| Layer | What it does | Where |
|---|---|---|
| Strict system prompt | "transcripts are your only source of truth, never invent" | Each prompt body |
| Verbatim quote requirement | LLM must emit copy-paste quotes, not paraphrases | Each prompt body |
| Post-process citation verify | `quote in transcript_body` string match per citation | After every LLM call |
| Retry on citation fail | 1 retry with explicit failure list in the next prompt | After 1st verify fail |
| `needs_manual_review` flag | Topic blocked from green ✓; UI shows red warning | After 2nd verify fail |
| Per-field traceability | Every field in extracted_snapshot links to a citation in evidence_trail | UI rendering + DB schema |

## 7. Backend changes

### 7.1 Endpoints

**Removed:**
- `BackgroundTask → run_verification_background` from `save_match_groups`
- `POST /api/calls/{cid}/topics/merge-preview` + `run_merge_preview`
- `_verify_merged_topics` (internal auto-pass)
- Polling for `merge_status` / `verification_status` on the project_updates page (replaced by per-pass status fields)

**Modified:**
- `POST /api/calls/{cid}/topics/save-matches` (`save_match_groups`): no longer triggers any background task. Just advances `kanban_stage` and sets the 3 new status fields to `idle`.

**New (one per button):**

| Endpoint | Trigger | Background? |
|---|---|---|
| `POST /api/calls/{cid}/topics/verify-new` | ① button | yes |
| `POST /api/calls/{cid}/topics/verify-not-discussed` | ② button | yes |
| `POST /api/calls/{cid}/topics/extract-updates` | ③ button | yes |

All 3 follow the same pattern as `run_extraction_background`: synchronous endpoint sets `<pass>_status = 'processing'`, spawns BackgroundTask, returns immediately. Frontend polls call data every 3s; on `<pass>_status = 'done'` it reads `<pass>_cache` and updates UI.

### 7.2 New workflow prompts in `artifact_library`

Three new entries seeded by `seed.py::SYSTEM_LIBRARY`, each with `is_system=true`, `seeded_by_default=true`.

| `category` | Default LLM | Default model | Notes |
|---|---|---|---|
| `verify_new_topic` | openrouter | anthropic/claude-sonnet-4-6:thinking (or equivalent) | reads all transcripts — needs 1M context |
| `verify_not_discussed` | openrouter | anthropic/claude-sonnet-4-6 (no thinking) | single transcript, lighter |
| `extract_topic_updates` | openrouter | anthropic/claude-sonnet-4-6:thinking | reads all transcripts, structured JSON output |

Model defaults are conservative recommendations; users can override per-project via `artifact_types`.

### 7.3 Deprecated workflow prompts

The 3 existing workflow prompts that this design replaces:

| Old `category` | What replaces it | Migration action |
|---|---|---|
| `project_topics` (merge prompt) | `extract_topic_updates` | Migration soft-deprecates: `is_system=false`, `seeded_by_default=false`. Existing artifact_types rows kept for rollback safety. |
| `merge_verification` | post-process citation verify (mechanical) | Same soft-deprecation. |
| `not_discussed_check` (old full-transcript blast) | `verify_not_discussed` (new lean version) | Same soft-deprecation. |

We don't hard-delete the old categories — they remain in DB but no code path resolves them anymore.

### 7.4 Data model

**New columns on `calls`:**

```sql
verify_new_status              TEXT     NOT NULL DEFAULT 'idle'
verify_new_cache               JSONB
verify_not_discussed_status    TEXT     NOT NULL DEFAULT 'idle'
verify_not_discussed_cache     JSONB
extract_updates_status         TEXT     NOT NULL DEFAULT 'idle'
extract_updates_cache          JSONB
```

(Old `verification_status` / `verification_cache` kept for rollback safety, no longer written.)

**New columns on `topic_updates`:**

```sql
citations       JSONB    -- per-field citations for the snapshot
evidence_trail  JSONB    -- chronological evidence trail across all calls
needs_manual_review BOOLEAN NOT NULL DEFAULT false
```

**Status field state machines:**

```
idle → processing → done
            ↓
          failed
```

`done` includes the case where some topics in the pass got `needs_manual_review` — failed verifications don't fail the pass overall, they just flag the individual topic.

### 7.5 Migration #030 (manual via Supabase dashboard)

1. `ALTER TABLE calls` — add 6 new status/cache columns
2. `ALTER TABLE topic_updates` — add `citations`, `evidence_trail`, `needs_manual_review`
3. `INSERT INTO artifact_library` — 3 new system entries (one per new category) with seeded_by_default=true
4. `UPDATE artifact_library` — soft-deprecate the 3 old workflow prompts (`is_system=false, seeded_by_default=false`)
5. Frontend code: backfill `seed_defaults` so existing projects get the 3 new artifact_types rows on next backend restart (or via a one-shot script)

## 8. UI changes summary

| File | Change |
|---|---|
| `frontend/src/components/ProjectUpdatesStage.tsx` | Major rewrite: 3-section layout with sequenced buttons. Remove auto-trigger of merge-preview. Add polling for the 3 new status fields. |
| `frontend/src/components/ProjectMatchingStage.tsx` | Minor: handler for `Save & Continue` no longer waits for background work. |
| `frontend/src/api/client.ts` | Add 3 new API methods (verifyNew, verifyNotDiscussed, extractUpdates). Remove `mergePreview`. |
| `frontend/src/types/index.ts` | Add types for the 3 new caches: `VerifyNewResult`, `VerifyNotDiscussedResult`, `ExtractedUpdate`, `Citation`, `EvidenceTrailEntry`. |
| `frontend/src/components/EvidenceTrail.tsx` (new) | Renders the chronological citation list with anchor links from snapshot fields. |
| `frontend/src/components/TopicCitationBadge.tsx` (new) | Small `[→ Call X cit-Y]` clickable tag. |

## 9. Acceptance criteria

- [ ] `Save & Continue` on `project_matching` no longer triggers any background LLM work; logs show only the DB advance.
- [ ] Landing on `project_updates` shows the 3-section layout with no LLM proposal pre-rendered.
- [ ] Buttons ② and ③ are disabled until ① is done. Same for ③ until ② is done.
- [ ] Clicking ① for a project with a "missed match" topic results in that topic migrating to section 3 with the `needs_extraction` flag.
- [ ] Clicking ② for a topic that WAS actually mentioned in call N migrates it to section 3 with a citation already attached.
- [ ] Clicking ③ produces a topic_update snapshot where every field has a citation, and the evidence_trail shows entries from every call where the topic appeared.
- [ ] Citation post-verify rejects any quote not found verbatim in the cited transcript. Retry happens automatically; second failure flags the topic.
- [ ] `Save & Continue → Artifacts` is disabled until all 3 buttons are done.
- [ ] Rollback to `project_updates` restores the cached results for all 3 passes (no re-LLM cost).
- [ ] Old TPM-blowing per-topic verify path is fully removed (no code path reaches it).

## 10. Downstream impact

### 10.1 Artifacts generation (next stage)

Topic data shape is unchanged at the surface (`summary`, `tasks`, `open_questions`, `decisions`, `status`, etc. still exist on `topic_updates`). Artifacts read the same fields. What changes is **quality + provenance**:

| Artifact | Today | After rework |
|---|---|---|
| `next_steps` (template) | tasks from auto-merge — may include hallucinated tasks | tasks grounded by citation, every task has a verbatim source quote |
| `executive_summary` (LLM) | summary drifts cumulatively call-over-call | summary re-derived from transcripts at each call — no drift |
| `decisions_digest` (template) | decisions from auto-merge | decisions anchored to verbatim quotes |
| `questions_list` (template) | OQ from auto-merge | OQ idem |
| Project-scope artifacts (any) | walks `topic_lineage` → assembles per-call evidence | walks identical, but each `topic_update` now has rich `evidence_trail` available |

**No breaking changes.** Existing artifact prompts continue to work — they read fields that still exist, just with cleaner content.

**Future enhancement (out of scope here):** artifact prompts can be upgraded to consume `citations` / `evidence_trail` and emit cited claims (e.g. "Decision X — [Call 1, line 220: 'let's defer to Q3']"). Tracked as a follow-up story.

### 10.2 Topics tab (historical cross-call view)

Components affected:

| Component | Change |
|---|---|
| `TopicsTimeline.tsx` | Unchanged. Continues to use `topic_lineage` for the matrix. New: small `⚠️` icon on cells where the underlying `topic_update.needs_manual_review = true`. |
| `TopicEvidenceDrawer.tsx` | Enriched. For calls where Pass ③ has run, additionally renders the `evidence_trail` as a chronological strip with verbatim citations per field. |
| `topics` parent table consumers (PreCallBrief, Dashboard) | Unchanged. |

### 10.3 Co-existence of `evidence` and `evidence_trail`

Both fields live on `topic_updates`. They are not redundant:

- `evidence` (existing field, populated by `call_topics` extractor) = quotes pulled from THIS call's transcript at extraction time, for this topic only
- `evidence_trail` (new field, populated by Pass ③) = chronological audit trail across calls 1..N produced by re-reading all transcripts with the topic as anchor

`evidence` is the INPUT (per-call extractor output). `evidence_trail` is the OUTPUT of Pass ③ (analyst-style cross-call review).

### 10.4 Old topic_updates (pre-migration)

Rows created before migration #030 have NULL `citations` and `evidence_trail`. UI degrades gracefully — drawer just doesn't render the evidence_trail section for those rows. Artifacts continue to read the core fields that have always existed.

---

## 11. Open questions / risks

- **Citation lines accuracy** — transcripts today don't carry line numbers in storage. The prompt asks for `lines: "X-Y"` but we'd compute these in post-process via `transcript_body.find(quote)` → derive a line range. Alternative: store line-indexed transcripts. Simplest path: derive on post-process, return `null` if quote not found (which also caps the citation-verify pass).
- **Cost ceiling per ③ click** — for a 10-call project with 20k tokens per transcript, ③ runs ~200k tokens of context × N merged topics. On Claude Sonnet 4.6 at ~$3/M input + $15/M output = ~$0.10-0.20 per click for typical N=3-5. Acceptable for single-user workflow.
- **What if call N's transcript is missing or empty?** ② degrades to "no transcript — cannot verify" message. ③ still works as long as it can read prior transcripts; the snapshot just won't have any "call N" entries in the evidence trail.
- **Citations storage size** — for a chatty topic across 10 calls, evidence_trail could hit 20-50 entries × ~200 bytes each = 4-10 KB per topic_update. JSONB on topic_updates is fine for this size. If it ever grows past 100 entries per topic, consider a dedicated `topic_update_citations` table.
- **Re-clicking ① after editing a topic in section 3** — current spec says re-clicking ① resets only section 1 results. If section 3 had `needs_extraction` topics promoted from section 1, those don't auto-revert. Need to confirm this is intended (vs. resetting all downstream).
