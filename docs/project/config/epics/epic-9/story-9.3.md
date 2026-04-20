# Story 9.3 — M:N ProjectMatchingStage UI

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §2.2
**Depends on:** Story 9.1

---

## Goal
Refactor ProjectMatchingStage to support selecting multiple left-side (existing project) topics. Enable M:N grouping: many left + many right → one merged group. Update "New →" to merge multiple right-side call topics into one output.

## Acceptance Criteria
- [ ] Multiple left-side topics can be selected simultaneously (all amber-highlighted)
- [ ] "Link ↔" creates a group with `project_topic_ids: [...selectedLeft]` (array, not single ID)
- [ ] Button label changes to "Merge ↔" when multiple left topics are selected
- [ ] "New →" with multiple right topics creates ONE group with `project_topic_ids: []` (not separate groups per topic)
- [ ] Left-side pills in an M:N group show the same group color and list all linked topics
- [ ] ✕ button on any pill in a group removes the entire group
- [ ] Existing single-match behavior (1 left + N right) works unchanged
- [ ] `topicsAPI.saveMatches()` sends `project_topic_ids` array format
- [ ] Saved match groups restore correctly on page reload / rollback

## Tasks
- [ ] Update `MatchGroup` type in `frontend/src/types/index.ts`
- [ ] Refactor `handleLink()` to use `project_topic_ids: [...selectedLeft]`
- [ ] Refactor `handleMarkNew()` to create single group for all selected right topics
- [ ] Update button label logic (Link vs Merge)
- [ ] Update left-side pill rendering for multi-topic groups
- [ ] Update `getProjectTopicGroup()` to check array membership
- [ ] Update `topicsAPI.saveMatches()` in `client.ts`
- [ ] Test group restore from backend (lowercase name remapping)

## Dev Tests
- Select 2 left + 3 right → Link → one group with 5 items, correct color
- Select 0 left + 3 right → New → one group (not 3 separate)
- Select 1 left + 1 right → Link → same as current behavior
- Remove group via ✕ → all items freed
- Save & reload → groups restore correctly
