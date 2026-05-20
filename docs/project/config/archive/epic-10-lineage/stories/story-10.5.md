# Story 10.5 — "+ new (merged)" Label on Timeline Cells

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.4, §6 Phase 4
**Depends on:** 10.3

---

## Goal
Visually distinguish merge-result topics from freshly-raised topics in the Topics Timeline. A topic created by M:N merging two sources should show "+ new (merged)" in a distinct color, with a tooltip listing source topic names.

## Detection rule
A topic is a merge-result iff at least one row exists in `topics WHERE merged_into_topic_id = {topic_id}`. The timeline API already knows every topic; we extend it to expose `has_sources: boolean` and `source_names: string[]` per topic.

## UI Requirements (visual mockup approval required)

**Fresh new topic (unchanged):**
- Cell label: `+ new`
- Color: green (current)

**Merge-result new topic (new):**
- Cell label: `+ new (merged)`
- Color: purple (distinct from green)
- Tooltip on hover: `Merged from: {source_names joined by ", "}`
- Icon: small merge-arrow glyph to the left of the label

**Evidence panel header (reinforcement):**
- For merge-result topics, the evidence panel header already shows a "Merged from: …" chip (Story 10.4). Confirm consistency with the tooltip text.

## Acceptance Criteria
- [ ] Timeline API response includes `has_sources: boolean` and `source_names: string[]` per topic
- [ ] `TopicsTimeline.tsx` renders "+ new (merged)" cells in purple when `has_sources === true`
- [ ] Tooltip on merge-result cells shows "Merged from: A, B" text
- [ ] Fresh new topics continue to render as "+ new" in green
- [ ] Other cell types (updated, not_discussed, merged/archived target) unchanged
- [ ] Visual mockup approved by user before code
- [ ] Unit test: given a topic with `merged_into_topic_id` pointing to it from 2 source topics, the timeline cell renders the merged-new variant
- [ ] Unit test: given a topic with no source rows, cell renders the fresh-new variant

## Tasks
- [ ] **Visual mockup** — extend the evidence panel mockup (Story 10.4) or build a dedicated timeline mockup showing the two cell variants side-by-side; get user approval
- [ ] Backend: extend the timeline endpoint in `backend/routers/topics.py` to return `has_sources` and `source_names` per topic
  - Single SQL query per topic: `SELECT name FROM topics WHERE merged_into_topic_id = {id}`
  - Or a batched lookup to avoid N+1
- [ ] Update `TimelineTopic` type in `frontend/src/types/index.ts` with `has_sources?: boolean; source_names?: string[]`
- [ ] Update cell renderer in `TopicsTimeline.tsx` to branch on `has_sources` for "new" cells
- [ ] Add CSS class + color token for `.timeline-cell-new-merged` (purple)
- [ ] Add tooltip (native `title` attribute or existing tooltip component) on merged-new cells
- [ ] Update Jest tests for `TopicsTimeline.tsx` with a fixture for a merge-result topic
- [ ] Manual QA on a seeded project with a mix of fresh and merge-result topics

## Dev Tests
- Seed a project with Call 1 raising topics A and B, Call 2 M:N-merging A+B into C → Timeline row for C shows "+ new (merged)" in purple at the Call-2 column
- Seed a project with Call 2 raising topic D (no merge) → Timeline row for D shows "+ new" in green at the Call-2 column
- Hover both cells to verify tooltip content

## Out of Scope
- Merge history visualisation on the archived source rows (Epic 10 current scope keeps archived rows as they are)
- Un-merge UI / manual merge undo (not in Epic 10)
