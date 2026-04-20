# Story 9.6 — Timeline: Merged Cell Type + Archive Filter

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §4
**Depends on:** Story 9.4

---

## Goal
Add "Merged → New Name" cells to the timeline for topics that were consolidated via M:N merge. Add a toggle to show/hide archived topics.

## Acceptance Criteria
- [ ] Topics with `merged_into_topic_id` show a "Merged → [name]" cell at the call where the merge happened
- [ ] "Merged" cell styled: grey background, italic, "↗ Merged" badge
- [ ] Merged topic rows show no cells after the merge call (topic is archived)
- [ ] Archive filter toggle above timeline table, default OFF
- [ ] Toggle label: "Show archived topics (N)" with count
- [ ] When ON: archived/merged topics appear at bottom with reduced opacity (0.5)
- [ ] When OFF: archived/merged topics hidden completely
- [ ] `list_topics_timeline()` accepts `include_archived` parameter

## Tasks
- [ ] Update `list_topics_timeline()` in `topics_service.py` to handle archived topics + merged cell type
- [ ] Add `include_archived` query param to timeline endpoint
- [ ] Add "merged" case to `Cell` component in `TopicsTimeline.tsx`
- [ ] Add archive filter toggle to `TopicsTimeline.tsx`
- [ ] Update `TimelineCell` type with `merged_into_name` field
- [ ] Style merged cell (grey, italic, badge)
- [ ] Update `topicsAPI.timeline()` to pass `include_archived` param

## Dev Tests
- Timeline shows "Merged → X" cell at correct call position
- No cells appear after the merge call for archived topics
- Toggle OFF: archived topics not visible
- Toggle ON: archived topics appear at bottom, dimmed
- Count badge updates correctly
