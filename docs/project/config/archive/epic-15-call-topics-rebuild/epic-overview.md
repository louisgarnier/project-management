# EPIC-15 — Call Topics Rebuild + Artifacts Rebuild + xlsx Tracker

**Phase 1 branch:** `epic-15-call-topics-rebuild` (merged into Phase 2 base)
**Phase 2 branch:** `epic-15-phase-2-artifacts`
**Phase 1 brainstorm / PRD / architecture:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-{brainstorm,prd,architecture}.md`
**Phase 2 brainstorm / PRD / architecture:** `docs/project/config/2026-05-18-epic-15-phase-2-{brainstorm,prd,architecture}.md`
**Mockups:** Phase 1 — `call-topic-tile-v3.html` (approved 2026-05-18); Phase 2 — `phase2-call-topics-extended.html`, `phase2-project-tracker-tab-v3.html` (approved 2026-05-18)

## Goal

**Phase 1** — Replace today's verbose, drifting call-topics output with sharp, evidence-anchored topics that map to clear `tasks[]`, surfaced in a row-per-task UI with full inline editing. Per-call prompt selection from the artifact library. System-seed model flip to `openrouter / deepseek-v3.2`.

**Phase 2** — Extend Phase 1 with `open_questions[]` + `decisions[]` per topic; replace the 2-value `context_scope` with a 4-value enum + context-assembly seam; add per-item lifecycle stamping + frozen chronology narratives + RAG verification; ship a 5-sheet xlsx tracker export and the Project Tracker sub-tab.

## Phase 1 Stories

| # | Story | Status | Depends on |
|---|---|---|---|
| 15.1 | [Schema + backend extractor + edit endpoints + prompt resolution](./story-15.1.md) | [x] code-complete — awaiting migration run | — |
| 15.2 | [Library seed: model flip + v2 call-topics entry](./story-15.2.md) | [x] done — 2026-05-18 | 15.1 |
| 15.3 | [Call Topics stage UI rewrite (v3 layout + inline edits + selector + popover)](./story-15.3.md) | [x] code-complete — awaiting visual smoke | 15.1, 15.2 |
| 15.4 | [Matching stage read-only display + real-fixture acceptance + rollback regression](./story-15.4.md) | [ ] todo | 15.1, 15.3 |

## Phase 2 Stories

| # | Story | Workstream | Status | Depends on |
|---|---|---|---|---|
| 15.5 | [Call-topics extension: open_questions + decisions](./story-15.5.md) | P2-A | [ ] todo | — |
| 15.6 | [`context_scope` 4-value enum + context-assembly seam](./story-15.6.md) | P2-B | [ ] todo | — (parallel-safe) |
| 15.7 | [Per-item lifecycle + chronology + RAG verification + accumulator](./story-15.7.md) | P2-C | [ ] todo | 15.5, 15.6 |
| 15.8 | [xlsx tracker exporter + ProjectTrackerTab + smoke acceptance](./story-15.8.md) | P2-D | [ ] todo | 15.7 |

**Dependency order:** 15.5 → 15.7 → 15.8 sequential; 15.6 runs in parallel with any of them.

## Definition of Done
- **Phase 1:** Stories 15.1–15.4 all `[x] done`. Real-fixture test (`backend/tests/test_real_fixture_4calls.py`) passes on smoke-test project with 4 FactSet transcripts. Rollback regression test passes. Manual-test walkthrough completed (see `docs/project/config/2026-05-18-epic-15-manual-tests.md`).
- **Phase 2:** Stories 15.5–15.8 all `[x] done`. xlsx export passes Excel + Google Sheets opens on smoke project. 5 sub-views render with chronology cells populated. Library seed idempotency test extended for 2 new system entries. Manual-test walkthrough updated (TBD: `docs/project/config/2026-05-19-epic-15-phase-2-manual-tests.md`).
- Per CLAUDE.md mandatory testing rule: real-transcript flow run end-to-end before declaring done.
