# EPIC-9: M:N Topic Merge + Not-Discussed Verification

> **Goal:** Replace the current 1:N topic matching with M:N matching (many existing topics + many call topics → one merged output), add RAG-quality merge synthesis using transcript excerpts, and automatically verify not-discussed topics against the transcript.

**Architecture:** Extends the existing project_matching → project_updates pipeline. Adds a `transcript_excerpt` field to `topic_updates` for primary-source grounding. Adds `merged_into_topic_id` on `topics` for merge tracking. Replaces `project_topic_id` (single UUID) with `project_topic_ids` (UUID array) on `topic_match_groups`. Adds a new workflow prompt category `not_discussed_check` for background verification. Timeline gets a new `merged` cell type and an archive filter toggle.

**Tech Stack:** Python/FastAPI (backend), Next.js/React (frontend), Supabase (Postgres), existing LLM service.

---

## 1. Data Model Changes

### 1.1 Migration: `018_mn_merge_and_verification.sql`

**`topic_updates` table — new column:**
- `transcript_excerpt TEXT DEFAULT NULL` — the relevant chunk of transcript that generated this topic update. Captured at extraction time by the LLM. Ensures merge prompts always work from primary sources, preventing "summary of summaries" information decay.

**`topics` table — new column:**
- `merged_into_topic_id UUID REFERENCES topics(id) ON DELETE SET NULL DEFAULT NULL` — when a topic is archived via M:N merge, points to the new combined topic. Used by timeline to render "Merged → New Name" cells. NULL for non-merged topics.

**`topic_match_groups` table — column swap:**
- Add `project_topic_ids UUID[] NOT NULL DEFAULT '{}'` — array of 0+ existing project topic IDs. Empty array = new topic group. Multiple entries = M:N merge.
- Migrate existing data: `UPDATE topic_match_groups SET project_topic_ids = ARRAY[project_topic_id] WHERE project_topic_id IS NOT NULL; UPDATE topic_match_groups SET project_topic_ids = '{}' WHERE project_topic_id IS NULL;`
- Drop `project_topic_id` column.

**`calls` table — new columns:**
- `verification_cache JSONB DEFAULT NULL` — stores per-topic verification results keyed by topic_id: `{topic_id: {discussed: bool, transcript_excerpt: str, reasoning: str}}`.
- `verification_status TEXT NOT NULL DEFAULT 'idle' CHECK (verification_status IN ('idle','processing','done','failed'))` — tracks background verification progress.

**`artifact_types` category constraint — add value:**
- Add `'not_discussed_check'` to the category check constraint (alongside `artifacts`, `topics`, `call_topics`, `project_topics`).

### 1.2 Frontend Type Changes

```typescript
// MatchGroup — project_topic_id replaced with project_topic_ids
type MatchGroup = {
  project_topic_ids: string[];    // empty = new topic, 1+ = linked/merge
  call_topic_names: string[];
};

// TimelineCell — new "merged" type
type TimelineCell = {
  type: "new" | "followed_up" | "not_discussed" | "pending" | "merged";
  merged_into_name?: string;      // only for type="merged"
  merged_into_topic_id?: string;  // only for type="merged"
  // ... existing fields unchanged
};

// TopicData — new optional fields
interface TopicData {
  // ... existing fields
  verification_status?: "pending" | "confirmed" | "flagged";  // not-discussed verification
}

// TimelineTopic — new field
interface TimelineTopic {
  // ... existing fields
  merged_into_topic_id?: string | null;
  merged_into_name?: string | null;
}
```

### 1.3 Backend Model Changes

```python
# topic_match_groups payload
class MatchGroupPayload(BaseModel):
    project_topic_ids: list[str] = []     # was: project_topic_id: Optional[str]
    call_topic_names: list[str]

# TopicUpdate — no changes needed (topic_id already handles new vs existing)
```

---

## 2. Feature 1: M:N Topic Matching + RAG Merge

### 2.1 Transcript Excerpt Capture

**When:** During `extract_call_topics()` (Step 1 of two-step extraction).

**How:** The extraction prompt is updated to ask the LLM to also return a `transcript_excerpt` field per topic — the verbatim or near-verbatim section of transcript that relates to this topic.

**Schema addition to extraction prompt:**
```json
{
  "name": "string",
  "summary": "string",
  "transcript_excerpt": "string — the relevant section of the transcript for this topic",
  "follow_up_items": ["string"],
  "decisions": ["string"],
  "status": "open|in_progress|resolved",
  "owner": "Us|Client|Both",
  "sentiment": "positive|neutral|concern"
}
```

**Storage:** The `transcript_excerpt` is carried through the pipeline in topic dicts and persisted to `topic_updates.transcript_excerpt` when `save_topics()` runs.

### 2.2 ProjectMatchingStage UI Changes

**Multi-select left side:**
- `selectedLeft` changes from selecting a single topic (used as `[...selectedLeft][0]`) to supporting multiple selections.
- Visual: multiple left pills can be amber-selected simultaneously.
- `handleLink()` creates a group with `project_topic_ids: [...selectedLeft]` instead of `project_topic_id: [...selectedLeft][0]`.

**"New →" with multiple right topics:**
- Currently creates separate new topics per call topic.
- Changes to: creates ONE group with `project_topic_ids: []` and all selected call_topic_names. The merge prompt will synthesize them into a single new topic with an LLM-proposed name.

**"Link ↔" label:**
- When multiple left topics selected, button label changes to "Merge ↔" to signal consolidation.

**Left-side pill display for M:N groups:**
- When a group has multiple `project_topic_ids`, all linked left pills show the same group color.
- The pill shows "↔ TopicA, TopicB, ..." listing all linked items (both left and right).

**Validation:**
- Unchanged: all call topics must be accounted for before "Save & Continue →".

### 2.3 Merge Pipeline Changes (`run_merge_preview`)

**Current behavior:**
- `merge_one(group)` handles two cases: `ptid is None` (new) and `ptid` set (matched).
- For matched: runs LLM with existing topic summary + call topics → merged summary.

**New behavior:**

For groups with `project_topic_ids` (1+ existing topics):
1. Collect all existing topic data from `prev_by_id` for each ID in `project_topic_ids`.
2. For each existing topic, load the full `transcript_excerpt` chain from `topic_updates` (all calls where this topic was discussed, ordered chronologically).
3. Load the call topics from `pending_by_name`.
4. Build a RAG-style merge prompt:
   ```
   You are merging project topics. Produce ONE output topic that synthesizes all history.

   [Project context]

   == Existing Topic: "UAT Access" ==
   Call 1 transcript excerpt: "..."
   Call 1 summary: "..."
   Call 3 transcript excerpt: "..."
   Call 3 summary: "..."

   == Existing Topic: "Environment Setup" ==
   Call 2 transcript excerpt: "..."
   Call 2 summary: "..."

   == New call topics from this call ==
   [call topic data with transcript_excerpt]

   Produce a merged topic with:
   - name: a concise name for the combined topic (propose a new name if merging multiple existing topics)
   - summary: synthesis of the full discussion history, grounded in the transcript excerpts
   - follow_up_items: current open items (max 5)
   - decisions: key decisions made across all calls
   - status / owner / sentiment: reflecting current state
   ```
5. Return `[{...merged, "topic_id": None, "_source_topic_ids": [...]}]` — the merged topic is always new (source topics get archived).

For groups with empty `project_topic_ids` (new topics from call):
1. If multiple call topics: build a merge prompt using their `transcript_excerpt` values to synthesize into ONE topic with an LLM-proposed name.
2. If single call topic: return as-is with `topic_id: None` (no LLM call needed).

### 2.4 Topic Archival on Save

When `validate_project_updates()` processes a merged topic (one whose `_source_topic_ids` field lists multiple source topics):
1. Create the new merged topic in `topics` table.
2. For each source topic ID in `_source_topic_ids`:
   - Set `merged_into_topic_id = new_topic_id` on the source topic.
   - Set `archived = True` on the source topic.
3. Create a `topic_update` for the new merged topic with the LLM-generated content + `transcript_excerpt`.

The `_source_topic_ids` field is an internal marker added by `merge_one()` and consumed by `validate_project_updates()`. It is not persisted to the DB and is stripped before saving. The frontend carries it through transparently in the `TopicData` dict.

For groups where `project_topic_ids` has exactly 1 entry (standard 1:1 match, no merge), the existing flow applies: the existing topic is updated in place with a new `topic_update` row. No archival occurs.

### 2.5 `save_match_groups` Backend Changes

- Accept `project_topic_ids: list[str]` instead of `project_topic_id: Optional[str]`.
- Store as `UUID[]` in the DB.
- Lowercase `call_topic_names` on save (unchanged).

---

## 3. Feature 2: Not-Discussed Verification

### 3.1 New Workflow Prompt Category

Add a seed `artifact_type` with:
- `category: "not_discussed_check"`
- `name: "Not-Discussed Verification"`
- Default prompt:
  ```
  You are checking whether a project topic was actually discussed in a call transcript.
  Given the topic name, its latest summary, and the full call transcript, determine:
  1. Was this topic mentioned or discussed in the call? (yes/no)
  2. If yes, provide the relevant transcript excerpt.

  Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null, "reasoning": "one sentence explanation"}
  ```

### 3.2 Backend: `verify_not_discussed_topics()`

New async function in `topics_service.py`:

1. Called as a background task when the user arrives at `project_updates` (triggered after `save_match_groups` advances to `project_updates`).
2. For each not-discussed topic:
   - Run the `not_discussed_check` prompt with the topic's latest summary + the call transcript.
   - If `discussed: true`: store the result in a new `verification_results` JSONB field on the `calls` table (keyed by topic_id).
3. Store results on the call row: `verification_cache: {topic_id: {discussed: bool, transcript_excerpt: str, reasoning: str}}`.
4. Add `verification_status` field to calls: `"idle" | "processing" | "done" | "failed"`.

### 3.3 Frontend: ProjectUpdatesStage Changes

**Not-discussed section updates:**
- Poll `verification_status` alongside `merge_status` (same 3s interval).
- When verification completes, topics flagged as "actually discussed" show:
  - Orange "⚠ Discussed in call" badge.
  - The LLM's reasoning text below.
  - A "Promote to Updated →" button.
- Topics confirmed as not-discussed show a subtle "✓ Confirmed" badge (green, small).

**Promote action:**
- Clicking "Promote to Updated →" moves the topic from `notDiscussed` array to a "Needs Merge" state (`pending_merge: true`).
- The user can then run the merge workflow to generate an updated summary for this topic.
- The `transcript_excerpt` from the verification result is carried into the merge prompt.

### 3.4 API Changes

**New endpoint:** `POST /calls/{call_id}/topics/verify-not-discussed`
- Triggers background verification.
- Returns immediately with `{"status": "processing"}`.

**Updated endpoint:** `GET /calls/{call_id}` (existing)
- Returns `verification_cache` and `verification_status` fields.

---

## 4. Timeline Changes

### 4.1 New "merged" Cell Type

When a topic has `merged_into_topic_id` set:
- At the call where the merge happened: show a "Merged → [New Name]" cell.
  - Styled: grey background, italic text, small "↗ Merged" badge.
  - The call where the merge happened = the `first_raised_call_id` of the merged-into topic.
- For all subsequent calls: no cells (topic is archived).

### 4.2 Archive Filter Toggle

Add a toggle button above the timeline table:
- Default: **off** (archived/merged topics hidden).
- Label: "Show archived topics" with a count badge.
- When on: archived topics appear at the bottom of the table with reduced opacity (0.5) and a "Merged" or "Archived" label in the topic name column.

### 4.3 `list_topics_timeline()` Changes

- Query `topics` table including archived topics when filter is on (new `include_archived` parameter).
- For topics with `merged_into_topic_id`: look up the merged-into topic's name for the "Merged → Name" cell text.
- New cell type `"merged"` added to the classification logic:
  - If `topic.merged_into_topic_id IS NOT NULL` and `call_id == merged_into_topic.first_raised_call_id` → type = "merged".

---

## 5. Rollback Considerations

### 5.1 `rollback_to_stage` Updates

**Rolling back to `project_matching`:**
- Same as today, plus: if any topics were archived with `merged_into_topic_id` set during this call's `validate_project_updates`, un-archive them and clear `merged_into_topic_id`.

**Rolling back to `call_topics`:**
- Same as today. The `transcript_excerpt` in `extraction_cache` is preserved (it's part of the topic dict).

**Rolling back to `project_updates`:**
- Same as today. `verification_cache` and `verification_status` are cleared (reset to idle/null).

### 5.2 New Cleanup: Un-merge on Rollback

When rolling back from `artifacts` (or later) to `project_updates` or `project_matching`:
1. Find topics where `merged_into_topic_id` points to a topic whose `first_raised_call_id` = this call.
2. Clear `merged_into_topic_id`, set `archived = False`.
3. Delete the merged-into topic (and its topic_updates).

---

## 6. Testing Strategy

### 6.1 Backend Unit Tests

- `test_mn_matching`: save_match_groups with `project_topic_ids` array (empty, single, multiple).
- `test_merge_preview_mn`: merge preview with 2 left + 2 right topics → single output topic with LLM-proposed name.
- `test_merge_preview_new_multi`: multiple call topics marked as new → single merged topic.
- `test_merge_preview_single`: single left + single right → same as current behavior (regression).
- `test_transcript_excerpt_capture`: extraction returns `transcript_excerpt` per topic, stored in `topic_updates`.
- `test_verify_not_discussed`: verification detects a discussed topic, returns correct result.
- `test_verify_not_discussed_confirmed`: verification confirms a genuinely not-discussed topic.
- `test_rollback_unmerge`: rolling back after merge un-archives source topics and deletes merged topic.
- `test_validate_with_merge_archival`: validate_project_updates archives source topics and sets `merged_into_topic_id`.

### 6.2 Frontend Component Tests

- ProjectMatchingStage: multi-select left, multi-select right, Link/Merge button label change, group display.
- ProjectUpdatesStage: verification badges, promote button, topic name editing.
- TopicsTimeline: merged cell rendering, archive filter toggle.

### 6.3 Integration Tests

- Full pipeline test: extract (with excerpts) → match M:N → merge preview (RAG) → validate (archival) → timeline (merged cells).
- Rollback test: advance through pipeline, rollback, verify un-merge.
- Not-discussed verification: arrive at project_updates, verification runs, promote flagged topic, re-run merge.

---

## 7. Migration Path

### 7.1 Backwards Compatibility

- Existing `topic_match_groups` rows with `project_topic_id` are migrated to `project_topic_ids` array in the migration SQL.
- Existing `topic_updates` rows have `transcript_excerpt = NULL` — merge prompts fall back to summary-only for historical data. New extractions will populate the field going forward.
- The `not_discussed_check` workflow prompt is seeded as a default artifact type on project creation (like other workflow prompts).

### 7.2 Migration Order

1. Run `018_mn_merge_and_verification.sql` in Supabase dashboard.
2. Deploy backend changes.
3. Deploy frontend changes.
4. Seed `not_discussed_check` artifact type for existing projects (one-time script or manual).

---

## 8. Files Affected

### Backend
- `backend/database/migrations/018_mn_merge_and_verification.sql` — new migration
- `backend/services/topics_service.py` — extraction prompt update, merge pipeline refactor, verify function, rollback updates
- `backend/routers/topics.py` — updated payload models, new verify endpoint
- `backend/routers/calls.py` — return verification fields
- `backend/routers/artifact_types.py` — seed not_discussed_check prompt

### Frontend
- `frontend/src/types/index.ts` — MatchGroup, TimelineCell, TopicData updates
- `frontend/src/components/ProjectMatchingStage.tsx` — multi-select left, merge UX
- `frontend/src/components/ProjectUpdatesStage.tsx` — verification badges, promote button
- `frontend/src/components/TopicsTimeline.tsx` — merged cell type, archive filter
- `frontend/src/api/client.ts` — updated API calls for new payload shapes
