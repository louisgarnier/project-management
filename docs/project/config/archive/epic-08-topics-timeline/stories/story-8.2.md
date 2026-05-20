# Story 8.2 — Topics Timeline Grid UI

**Epic:** EPIC-8 — Topics Timeline Grid
**Status:** `pending`

---

## Goal
Replace the flat `TopicsDashboard` on the Board's Topics tab with a horizontally scrollable timeline grid: rows = topics (fixed left column), columns = one per call.

## Approved Mockup
Design approved 2026-04-15. Exact visual spec:
- Left column sticky (220px): topic name (12px bold) + badges row (status + sentiment + owner)
- Call columns (180px each): header = "Call N" (bold) + truncated title (grey)
- Horizontally scrollable; left column stays fixed
- Resolved rows at 65% opacity
- Cell states:
  - **Absent**: blank cell
  - **Not discussed**: grey "—" centered
  - **New ✦**: orange badge (`#ff8b00` bg, white text) + 2-line summary + follow-up count + click to expand full detail
  - **Updated**: blue badge (`#0052cc`) + 2-line summary + follow-up count + click to expand
  - **✓ Resolved**: green badge (`#006644`) + 2-line summary (no expand needed)
- Expand panel (on click for New/Updated): full summary + labeled follow-up list with "→" prefix
- Collapse toggle: "▾ expand" / "▴ collapse"

## Acceptance Criteria
- [ ] Board → Topics tab renders `TopicsTimeline` (replaces `TopicsDashboard`)
- [ ] Fixed left column: topic name + current status/owner/sentiment badges
- [ ] One 180px column per call, header shows "Call N" + truncated title
- [ ] Grid scrolls horizontally; left column stays sticky
- [ ] Cell states as per approved mockup above
- [ ] Click New/Updated cell → expands to show full summary + full follow-up list
- [ ] Click again → collapses
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
