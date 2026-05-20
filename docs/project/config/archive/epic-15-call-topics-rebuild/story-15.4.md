# Story 15.4 — Matching Stage Read-Only Display + Real-Fixture Acceptance + Rollback Regression

**Epic:** EPIC-15 — Call Topics Rebuild
**Status:** [ ] DEFERRED to Phase 3 (moved 2026-05-19)
**Spec:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md` §3.2 (matching display) + §10 (test strategy)
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md` G6, G9, G10, US-08, US-09, US-10
**Depends on:** Story 15.1 (aggregate endpoint must return new fields), Story 15.3 (popover component must exist for reuse), **Phase 2 closing the pipeline end-to-end**

**Deferral rationale (user, 2026-05-19):** Call 1 has no matching phase, so the matching-UI gap does not block Phase 2 / artifacts work. The real-fixture and rollback tests require an end-to-end working pipeline, which Phase 2 must deliver first. Do not start this story during Phase 2. When Phase 2 closes, re-scope as the opener for Phase 3.

## Goal
1. Surface the new topic fields (`key_terms` / `evidence` / `tasks`) **read-only** in the project-matching stage UI so the user can use them during manual matching.
2. Validate the full pipeline against the 4 real FactSet transcripts on the smoke-test project (per CLAUDE.md mandatory testing rule).
3. Add a regression test covering rollback semantics — re-extracting call N must roll back later calls to call_topics stage.

## Acceptance Criteria

### Frontend — read-only matching display
- [ ] `frontend/src/components/TopicsDashboard.tsx` (project-matching view): for each topic, render:
  - [ ] Key-term chips (same styling as call_topics stage)
  - [ ] 📄 evidence indicator with the styled hover popover (reuse the component from Story 15.3 — no duplication)
  - [ ] Compact tasks summary: each task as a single line with task text + status badge. No edit affordances. No add/delete buttons.
- [ ] `frontend/src/components/TopicsPanel.tsx`: same render rules where applicable.
- [ ] No PATCH/DELETE calls fire from anywhere in the matching UI. No edit handlers wired.
- [ ] Visual: fields are visible by default — no extra click needed to reveal chips / evidence / tasks (US-10 AC).

### Backend tests — real-fixture acceptance
- [ ] `backend/tests/test_real_fixture_4calls.py` extended (gated `@pytest.mark.realfixture`):
  - [ ] Runs all 4 FactSet transcripts on the smoke-test project (`17e2687f-bdd8-43ee-88a7-d2bd79a13925`) through the new pipeline end-to-end.
  - [ ] Asserts every extracted topic carries ≥1 `evidence` reference and ≥1 task.
  - [ ] Asserts no topic has the legacy fields (`decisions`, `follow_up_items`, etc.) — confirms the migration + new shape are end-to-end.
  - [ ] Asserts topic names are visibly tighter than the EPIC-11 baseline (concrete check: average topic name ≤ 60 characters on the FactSet corpus, vs current baseline of ~90; OR a manual diff committed alongside the test for human review).
  - [ ] Asserts matching aggregate endpoint payload now includes `key_terms`, `evidence`, `tasks`.

### Backend tests — rollback regression
- [ ] Same fixture test adds a rollback scenario:
  - [ ] After all 4 calls reach a stage past `call_topics`, re-trigger `extract_call_topics(call_2_id)`.
  - [ ] Assert calls 3 and 4 are now in `kanban_stage = 'call_topics'` (rolled back).
  - [ ] Assert call 2's existing topic_updates are replaced (old rows gone, new rows from the new extraction).

### Manual test doc
- [ ] `docs/project/config/2026-05-18-epic-15-manual-tests.md` — step-by-step walkthrough of:
  - [ ] Open smoke-test project → arrive at call_topics for Call 1 → select v2 prompt → re-extract → verify v3 UI layout.
  - [ ] Edit a task inline (status drop), add a task, delete a task, delete a topic → verify persistence.
  - [ ] Advance to matching stage → verify chips + evidence popover + tasks list appear read-only.
  - [ ] Repeat for Calls 2–4. After all 4 done, re-extract Call 2 and verify Calls 3 + 4 rolled back.

## Out of scope (in this story)
- Any further frontend rewrite of call_topics stage (closed in Story 15.3).
- Library seed changes (Story 15.2).
- xlsx / Phase-2 deferred-epic work — entirely out of EPIC-15.

## Definition of Done for EPIC-15
All 4 stories `[x] done`, real-fixture test passes, rollback regression passes, manual-test walkthrough completed and notes appended to this story.
