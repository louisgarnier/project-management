# Story 10.7 — Call Topics Stage: Evidence Drawer

**Epic:** EPIC-10 — Topic Lineage + Full-Stage Traceability + Prompt Quality
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.3, §6 Phase 5
**Depends on:** 10.4

---

## Goal
When the user views the Call Topics stage (the list of topics extracted from the current call), clicking any extracted topic opens the evidence drawer showing the data that caused that topic to be extracted — the verbatim transcript excerpt, the extracted summary, follow-ups, and decisions.

This is the simplest of the per-stage evidence surfaces: no new backend work, uses existing `calls.pending_topics` data, reuses the `TopicEvidenceDrawer` component from Story 10.4 in `mode="call_topic"`.

## UI Requirements (mockup approved via `project-matching-drawer-compare.html`, full-overlay drawer)

- Each topic card on the Call Topics stage gets a "Show source" link (or makes the entire card clickable).
- Clicking opens the full-overlay drawer (same pattern as Story 10.4).
- Drawer title: the extracted topic name.
- Drawer body, single panel:
  - **Transcript excerpt** (verbatim, italic, quoted style) — labelled "Extracted from:"
  - **Summary** (the LLM's summary of the extraction)
  - **Follow-ups** (bulleted; muted "(none)" if empty)
  - **Decisions** (bulleted; muted "(none)" if empty)
  - **Status / Owner / Sentiment** chips
- If `transcript_excerpt` is `null` (pre-migration topic or missing), show muted "(No excerpt captured for this call)".
- Close via X button, Esc key, or click outside.

## Acceptance Criteria
- [ ] `TopicEvidenceDrawer` supports `mode="call_topic"` with `pendingTopic` prop
- [ ] `CallTopicsStage.tsx` (or equivalent component) attaches click handler to each topic card
- [ ] Drawer opens with pending_topic data; no network call needed (data already in Redux/component state)
- [ ] All pending topic fields rendered per UI requirements
- [ ] Drawer closes cleanly; no scroll jump on underlying view
- [ ] Works for both pre-submission pending topics (`calls.extraction_cache`) and post-submission pending topics (`calls.pending_topics`)
- [ ] Unit test: renders drawer with mock pending topic, asserts all fields present
- [ ] Manual QA: extract topics from a seeded call, click each, confirm drawer opens with correct data

## Tasks
- [ ] Extend `TopicEvidenceDrawer` (from Story 10.4) with a `mode="call_topic"` branch rendering the single-panel layout
- [ ] Update `CallTopicsStage.tsx` to render a clickable affordance on each topic card and manage drawer open state
- [ ] Pass pending_topic data (name, summary, follow_up_items, decisions, transcript_excerpt, status, owner, sentiment) as `pendingTopic` prop
- [ ] Handle both extraction_cache (pre-submission) and pending_topics (post-submission) data shapes
- [ ] Jest component test for the `call_topic` mode rendering
- [ ] Manual QA checklist executed

## Dev Tests
- Extract topics on a seeded call; click each extracted topic; confirm drawer shows the correct transcript_excerpt verbatim
- Click a topic whose excerpt is `null`; confirm the muted fallback renders
- Tab-focus the topic card; confirm keyboard activation opens the drawer

## Out of Scope
- Editing pending topic fields from the drawer (read-only)
- Comparing the current call extraction against prior calls (that is `mode="matching"` in Story 10.8)
- Full-transcript view with highlighted excerpt (explicitly not wanted per user decision 2026-04-20)
