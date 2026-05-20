# Story 10.4 — Evidence Drawer UI — Lineage Mode (Color-Coded Per-Call Trail)

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.3, §6 Phase 3
**Depends on:** 10.3

---

## Goal
Build the reusable `TopicEvidenceDrawer` React component in its `mode="lineage"` configuration — a full-overlay drawer (approved via mockup 2026-04-20) that displays the complete per-call evidence trail for a topic, color-coded by call — and mount it on the Project Updates stage + the Topics Timeline. The same component is extended in Stories 10.7 (`mode="call_topic"`) and 10.8 (`mode="matching"`) to cover the remaining Kanban stages.

## UI Requirements (must pass visual mockup approval before any code)

**Header zone:**
- Topic name as title
- Lineage chip: "Merged from: Topic A, Topic B" (only shown when `lineage.length > 1`)
- Close button (drawer dismissal)

**Card list:**
- One card per `calls[]` entry, chronological order (oldest first, top to bottom)
- Call-index-based color palette: 8 distinct pastels cycled by call index; stable for a given call title
- Card header: call title · call date · if `source_topic_id !== topic_id` show provenance badge "from archived topic: {source_topic_name}"
- Card body (always visible):
  - Transcript excerpt — italic, quoted style, `null` → muted "(No excerpt captured for this call)"
  - Merged summary — "After this call:" label
  - Follow-ups — bulleted list; if empty, muted "(none)"
  - Decisions — bulleted list; if empty, muted "(none)"
  - Status badge (open/in_progress/resolved)
- Card expandable details (collapsed by default):
  - Raw pre-merge extract (if present): "Raw from Call N:" with summary + follow-ups + decisions
  - Match group (if present): "Matched with: {project_topic_ids → names}, grouped with call topics: {call_topic_names}"
  - Not-discussed verification (if present): discussed badge + excerpt + reasoning

**Empty state:**
- If `calls[]` is empty: "No evidence available for this topic."

## Acceptance Criteria
- [ ] New component `frontend/src/components/TopicEvidenceDrawer.tsx` consumes `GET /api/topics/{id}/evidence` via `api/client.ts`
- [ ] Rendered as a full-overlay drawer (approved pattern 2026-04-20) that dims the underlying view; close returns to the previous state
- [ ] Per-call cards color-coded via 8-color palette cycled by call index
- [ ] Lineage chip visible only for merge-result topics
- [ ] Provenance badge visible on ancestor-source cards
- [ ] Raw extract / match group / verification sections collapsed by default, expandable per section
- [ ] Loading state while fetching; error state with retry button on fetch failure
- [ ] Mounted on Project Updates stage: expandable "View evidence" link under each Updated Topic card
- [ ] Mounted on Topics Timeline: clicking any timeline cell opens the drawer for that topic
- [ ] Closing the drawer preserves scroll position on the underlying view
- [ ] Accessible: close via Esc key, focus trap within drawer, ARIA labels on interactive elements
- [ ] Visual mockup approved by user before code is written

## Tasks
- [ ] **Visual mockup first** — invoke `ui-mockup:ui-mockup` skill, render interactive HTML, get user approval
- [ ] Add `fetchTopicEvidence(topicId)` to `frontend/src/api/client.ts`
- [ ] Add TypeScript types mirroring the backend response (`TopicEvidence`, `EvidenceCall`, `LineageNode`, etc.) in `frontend/src/types/index.ts`
- [ ] Implement `TopicEvidenceDrawer.tsx` as a controlled full-overlay drawer (open/close via props, `mode` prop accepting `"lineage" | "call_topic" | "matching"`; this story ships `"lineage"` only)
- [ ] Implement color-palette helper (`getCallColor(callIndex)`) — 8 pastel swatches
- [ ] Implement per-card expandable sections (raw extract, match group, verification)
- [ ] Integrate into `ProjectUpdatesStage.tsx`: add "View evidence" link per updated topic; manage drawer open state
- [ ] Integrate into `TopicsTimeline.tsx`: make timeline cells clickable; open drawer for the topic
- [ ] Add Jest component tests: loads evidence, renders lineage chip for merged topic, renders cards in order, expands sections
- [ ] Manual QA: test on a seeded project with 3 calls + 1 M:N merge

## Dev Tests
- Seed a project with 3 calls + 1 M:N merge
- From the Project Updates stage on Call 3, click "View evidence" on an updated topic; confirm drawer opens with 3 color-coded cards
- Click Timeline cell on a merge-result topic at Call 2; confirm drawer shows lineage chip and evidence from both source topics
- Test loading, error, and empty states by mocking the API response

## Out of Scope
- Merge-result labeling on Timeline cells (Story 10.5)
- Editing evidence entries (read-only)
- Export / print of evidence panel
- Infinite scroll or pagination (not needed for expected scale)
