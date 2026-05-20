# Story 10.8 — Project Matching Stage: Side-by-Side Evidence Drawer

**Epic:** EPIC-10 — Topic Lineage + Full-Stage Traceability + Prompt Quality
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.3, §6 Phase 5
**Depends on:** 10.3, 10.4

---

## Goal
On the Project Matching stage, every match decision (followed-up, new, not-discussed) has a "Show evidence" affordance that opens the full-overlay evidence drawer in `mode="matching"` — a two-column layout that lets the user see the reasoning for the classification by reading the source data on both sides.

**No LLM classification reasoning is persisted** (user decision 2026-04-20). The user understands the decision by inspecting the data: left column shows the existing project topic's full lineage evidence, right column shows the current call's extraction for the matched call topic. This gives a clear historical trace of "why we are where we are" on that topic.

## UI Requirements (mockup approved via `project-matching-drawer-compare.html`, full-overlay drawer)

**Trigger:** "Show evidence" link on each match row. Works for all three classification types.

**Layout:** Full-overlay drawer, two-column grid inside.

**Left column — Existing topic history:**
- Reuses `mode="lineage"` content renderer (color-coded per-call cards from Story 10.4)
- For `kind="new"`: empty state "No existing project topic matches this subject"

**Right column — Current call extraction:**
- Card showing the pending call topic's `transcript_excerpt` + summary + follow-ups + decisions + status/owner/sentiment
- For `kind="not_discussed"`: empty state "Not extracted from this call"

**Footer strip (small, derived from data shown — not persisted LLM output):**
- `followed_up`: "Matched because the same subject appears across {N} prior call(s), and Call {current}'s extraction aligns with that subject."
- `new`: "Marked new because no existing project topic matches the subject of this call extraction."
- `not_discussed`: "Marked not-discussed because the LLM found no call topic in Call {current} on this subject."

**Close:** X button, Esc, or click outside → returns to matching view.

## Backend Requirements
- Extend the project-matching GET endpoint (or the matches-with-pending response used by `ProjectMatchingStage.tsx`) to include the pending_topic data inline for each match row. This avoids a second API call on every drawer open.
- No new endpoint. No new DB columns.

## Acceptance Criteria
- [ ] `TopicEvidenceDrawer` supports `mode="matching"` with a two-column layout
- [ ] Each match row on `ProjectMatchingStage.tsx` has a clickable "Show evidence" affordance
- [ ] Clicking opens the drawer with correct left/right content per `kind`
- [ ] Left column reuses `mode="lineage"` rendering for the existing topic (fetches `/api/topics/{id}/evidence`)
- [ ] Right column renders pending_topic data directly from the matches response (no extra fetch)
- [ ] Empty states render correctly for `new` (empty left) and `not_discussed` (empty right)
- [ ] Footer strip shows the data-derived explanation per `kind`
- [ ] Closing the drawer preserves scroll and selection state on the matching view
- [ ] Unit tests for all three kinds (`followed_up`, `new`, `not_discussed`)
- [ ] Manual QA on a seeded project with matches of each kind

## Tasks
- [ ] Backend: extend matches response in `backend/routers/topics.py` to embed pending_topic data per match row (check if already included; if not, join from `calls.pending_topics`)
- [ ] Frontend: extend `TopicEvidenceDrawer` with `mode="matching"` renderer (two-column grid + footer strip)
- [ ] Update `ProjectMatchingStage.tsx` to add "Show evidence" link on each row and manage drawer open state with mode + props
- [ ] Implement footer-strip logic deriving explanation from `kind` + counts
- [ ] Jest component tests for the three `kind` variants
- [ ] Manual QA on a 3-call seeded project with a mix of classifications

## Dev Tests
- Seed a project with Call 1 (topic A raised), Call 2 (topic A matched, topic B new, topic C not-discussed)
- On Project Matching for Call 2, click "Show evidence" on each of the 3 rows; confirm drawer opens with correct data and layout per `kind`
- Verify left column correctly renders ancestor-aware lineage (via Story 10.3 endpoint) when the existing topic is M:N-merged

## Out of Scope
- Persisting the LLM's classification reasoning (explicitly deferred — user decision 2026-04-20)
- Inline re-classification from the drawer (keep existing Project Matching UI drag/select for re-assignment; drawer is read-only)
- Full-transcript view
