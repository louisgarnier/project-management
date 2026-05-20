# Story 10.9 — Timeline Item Provenance + Ancestor Visualization

**Epic:** EPIC-10 — Topic Lineage + Full-Stage Traceability + Prompt Quality
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-21-story-10.9-timeline-provenance-design.md`
**Depends on:** 10.1, 10.3, 10.4, 10.5 (all shipped)

---

## Goal
Surface per-item provenance (pills showing which call first contributed each follow-up/decision) directly on Timeline cells + Evidence Drawer, AND render archived-ancestor topics as indented rows under their merge-result row (toggled via a chevron), so users can trace lineage without leaving the grid.

## UI Requirements (mockup approval required before any code per user CLAUDE.md rule)

**Provenance pills:**
- Compact pill: background color from 8-color palette (cycled by call index), text `C{index+1}` (1-indexed for readability), tooltip shows full call title on hover
- Rendered next to each follow-up item and each decision item, in:
  - Timeline cells (expanded view — one pill per item)
  - Timeline cells (collapsed summary — shows "3 follow-ups (C1–C3)" inline summary using unique origin-call set)
  - `TopicEvidenceDrawer` CallCard items (same rendering)
- `?` fallback pill (muted) when item not found in any prior cell's history (LLM rewording)

**Ancestor-row chevron:**
- On every merge-result topic row (`has_sources === true` — from Story 10.5), a chevron button (▸/▾) appears to the left of the topic name
- Click toggles that topic's archived-ancestor rows as indented children directly below the merge-result row
- Archived rows render with: 16px indent, `├─` / `└─` tree connector, strikethrough topic name, dimmed color
- Each ancestor row renders full cell-by-cell data (same as a regular row) but with:
  - Cell at merge-call column: `Merged ↗` badge + "→ folded into {merge-result name}" annotation
  - Cells after merge column: muted "(archived)" text
  - Cells before merge column: normal summary + follow-ups (with pills) + decisions (with pills)
- Global "Show archived" toggle renamed to "Expand all lineage" — toggling ON adds all merge-result IDs to `expandedLineageIds`; OFF clears

**Interaction parity:**
- Clicking an archived ancestor's topic name opens `TopicEvidenceDrawer` for that ancestor (leaf lineage — just its own history)
- "Show evidence" link per cell still works on archived rows

## Acceptance Criteria
- [ ] New backend helper `get_ancestors_by_target(project_id, db)` returns `{merge_target_id: [ancestor_ids]}` map
- [ ] `list_topics_timeline` response includes `ancestor_topic_ids` on each merge-result active topic and `merge_call_id` on each archived topic
- [ ] New frontend component `ProvenancePill.tsx` renders a compact pill with call index + tooltip
- [ ] New frontend utility `provenance.ts::resolveProvenance()` pure-function resolves item → origin call via exact-string match, returns null on miss
- [ ] Timeline cell expanded view shows one pill per follow-up and decision item
- [ ] Timeline cell collapsed summary shows unique origin-call set summary (e.g., "3 follow-ups (C1, C2)")
- [ ] Evidence Drawer CallCard items show the same pill component
- [ ] Merge-result rows have a chevron; clicking expands indented ancestor rows directly below
- [ ] Ancestor rows have tree connector, indentation, strikethrough, `Merged ↗` badge on the merge-call cell, "(archived)" on later cells
- [ ] Clicking an ancestor's topic name opens Evidence Drawer for that ancestor
- [ ] "Show archived" toggle renamed to "Expand all lineage" and expands/collapses all at once
- [ ] Visual mockup approved by user before code ships
- [ ] All Epic-10 existing tests still green; new backend unit test asserts `ancestor_topic_ids` + `merge_call_id` populated correctly
- [ ] Manual smoke on AAAA project confirms the full flow works end-to-end

## Tasks
- [ ] Visual mockup (interactive HTML via ui-mockup skill) — user approval gate
- [ ] Backend: `get_ancestors_by_target` helper + `list_topics_timeline` extension + test
- [ ] Frontend types: extend `TimelineTopic` with `ancestor_topic_ids`, `merge_call_id`
- [ ] Frontend utility: `provenance.ts::resolveProvenance()` + manual test
- [ ] Frontend component: `ProvenancePill.tsx`
- [ ] Frontend: extract shared `CALL_COLORS` palette constant (currently duplicated in `TopicEvidenceDrawer`)
- [ ] Frontend: `TopicsTimeline.tsx` — chevron on merge-result rows, ancestor-row insertion, pills in cells
- [ ] Frontend: `TopicEvidenceDrawer.tsx` — swap inline item rendering for `ProvenancePill`
- [ ] Type-check with `npx tsc --noEmit` (do NOT `npm run build` during dev — per feedback)
- [ ] Manual smoke on AAAA
- [ ] Update `build-log.md`, `codebase.md`, `ACTIVE.md`, `overview.md`
- [ ] Commit each phase with `[EPIC-10]` prefix; push at the end

## Dev Tests
- Backend: seed a project with Call 1 (raises A, B, C), Call 2 (M:N-merges A+B+C into D). Call `list_topics_timeline(project_id)` → assert D has `ancestor_topic_ids = [A, B, C]` (sorted by created_at), and each archived row has `merge_call_id = Call 2`.
- Frontend provenance utility: seed history `[Call1: ['a','b'], Call2: ['a','b','c']]`. Current items `['a','b','c']` → origin calls `[Call1, Call1, Call2]`. Item `'x'` → null.
- Smoke on AAAA: expand "Risk Analytics and EDS Integration" (a 3-source merge-result) → verify 3 ancestor rows indented, each with its own Call-1 data. Hover pills to verify tooltips. Click an ancestor's name → Evidence Drawer opens.

## Out of Scope
- Fuzzy item matching (reworded items fall back to `?` pill)
- Multi-level lineage indentation (only direct parents shown; deeper chains accessible via Evidence Drawer)
- Mobile layout
- Keyboard navigation
