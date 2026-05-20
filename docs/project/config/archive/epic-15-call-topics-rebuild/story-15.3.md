# Story 15.3 — Call Topics Stage UI Rewrite

**Epic:** EPIC-15 — Call Topics Rebuild
**Status:** [x] done — 2026-05-18 (code-complete; awaiting user visual smoke test)
**Spec:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md` §3.2
**Approved mockup:** `call-topic-tile-v3.html` (rendered in the local mockup server on 2026-05-18, approved)
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md` G4, G5, G7, US-01, US-02, US-03, US-04, US-05, US-06, US-07, US-11
**Depends on:** Story 15.1 (backend endpoints + types must be live); Story 15.2 (library seed must contain v2 entry so the selector has content)

## Goal
Replace the EPIC-11 3-section coloured tile with the v3 flat-table layout: one row per task, topic name + key-term chips repeated on every row, styled hover popover for evidence, inline editing for every field, prompt-variant selector at the top of the stage. Delete `TopicEditor.tsx` and `TopicEvidenceDrawer.tsx`.

## Acceptance Criteria
- [x] `frontend/src/types.ts`:
  - [x] `TopicData` reshaped: adds `key_terms: string[]`, `evidence: EvidenceRef[]`, `tasks: TaskData[]`. Removes legacy fields.
  - [x] New types: `EvidenceRef = { speaker, quote, citation }`, `TaskData = { task_id, task, next_step, status: 'open'|'in_progress'|'resolved', owner }`.
  - [x] `Call` gets `call_topics_prompt_id: string | null`.
- [x] `frontend/src/components/CallTopicsStage.tsx` rewritten:
  - [x] Renders a single flat table (no per-topic tile wrapper).
  - [x] One row per task. Topic name + key-term chips repeated in the leftmost cell on every row.
  - [x] Columns: Topic+chips | Task | Next step | Owner | Status | Evidence (📄) | Actions.
  - [x] Inline edits (debounced, ~400ms) via PATCH `/api/topics/{id}`:
    - [x] Topic name (click-to-edit)
    - [x] Importance dropdown (HIGH / MED / LOW)
    - [x] Key terms: × per chip + `+ term` input
    - [x] Evidence: add / remove / edit references (modal or expanded editor — implementation choice)
    - [x] Task text, next_step text, owner text (click-to-edit cells)
    - [x] Status dropdown (OPEN / IN PROGRESS / RESOLVED)
  - [x] Per-row × deletes that task (rebuilds tasks[] minus that task_id, PATCHes the topic).
  - [x] Per-topic footer: `+ Add task to "<topic>"` button + `🗑 Delete topic` button (with confirmation).
  - [x] Evidence indicator (📄) opens a styled hover popover: white background, soft border, one block per `EvidenceRef`, speaker bold + quote italic + citation small grey.
  - [x] **Prompt-variant selector** at the top of the stage: `<select>` populated from `GET /api/library?category=call_topics`. Default value = `calls.call_topics_prompt_id` or library's `seeded_by_default=true` entry. On change → PATCH the call's prompt id.
- [x] **Delete** `frontend/src/components/TopicEditor.tsx`.
- [x] **Delete** `frontend/src/components/TopicEvidenceDrawer.tsx`.
- [x] `frontend/src/components/TopicsDashboard.tsx` + `TopicsPanel.tsx`: reshape to read new `TopicData` types — but matching-stage read-only rendering is Story 15.4. In this story, just make them compile + read the new fields without crashing.
- [x] `frontend/src/api/client.ts` types updated.
- [x] `npx tsc --noEmit` clean (per project rule — never `npm run build` during dev).
- [x] ESLint clean (0 errors, 5 warnings — all pre-existing unused-var warnings, acceptable).
- [ ] Visual: the rendered stage matches `call-topic-tile-v3.html` in structure (columns, repeated topic+chips per row, evidence popover, all editable affordances). **awaiting user visual smoke test**

## Out of scope (in this story)
- Read-only matching-stage display polish (Story 15.4).
- Real-fixture acceptance + rollback regression test (Story 15.4).
- Backend changes (Story 15.1).
