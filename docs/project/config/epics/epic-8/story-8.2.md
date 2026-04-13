# Story 8.2 — Topics Timeline Grid UI

**Epic:** EPIC-8 — Topics Timeline Grid
**Status:** `pending`

---

## Goal
Replace the flat `TopicsDashboard` on the Board's Topics tab with a horizontally scrollable timeline grid: rows = topics (fixed left column), columns = one per call.

## Acceptance Criteria
- [ ] Board → Topics tab renders `TopicsTimeline` (replaces `TopicsDashboard`)
- [ ] Fixed left column: topic name + current status/owner/sentiment badges
- [ ] One 160px column per call, header shows "Call N" + truncated title
- [ ] Grid scrolls horizontally; left column stays fixed (sticky)
- [ ] Cell states:
  - **Absent**: blank
  - **Not discussed**: grey "—"
  - **New ✦**: orange badge + 2-line summary
  - **Updated**: blue badge + 2-line summary + follow-up count
  - **✓ Resolved**: green badge
- [ ] Resolved topic rows at 65% opacity
- [ ] Empty state: appropriate message when no topics or no calls
- [ ] `TopicsTimelineData`, `TimelineCell`, `TimelineTopic` types in `frontend/src/types/index.ts`
- [ ] `topicsAPI.timeline(projectId)` in `frontend/src/api/client.ts`

## Tasks
- [ ] Add types to `frontend/src/types/index.ts`
- [ ] Add `topicsAPI.timeline` to `frontend/src/api/client.ts`
- [ ] Create `frontend/src/components/TopicsTimeline.tsx`
- [ ] Update `frontend/app/projects/[id]/board/page.tsx` to render `TopicsTimeline` on Topics tab

## Dev Tests
- Manual: Board → Topics tab → grid shows with call columns
- Manual: topic first raised in call 2 → call 1 column is blank
- Manual: resolved topic → row at 65% opacity, green "✓ Resolved" badge
