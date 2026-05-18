# EPIC-15 — Call Topics Rebuild

**Branch:** `epic-15-call-topics-rebuild`
**Brainstorm:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-brainstorm.md`
**PRD:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-prd.md`
**Architecture:** `docs/project/config/2026-05-18-epic-15-call-topics-rebuild-architecture.md`
**Mockup:** `call-topic-tile-v3.html` (approved 2026-05-18)

## Goal
Replace today's verbose, drifting call-topics output with sharp, evidence-anchored topics that map to clear `tasks[]`, surfaced in a row-per-task UI with full inline editing. Per-call prompt selection from the artifact library. System-seed model flip to `openrouter / deepseek-v3.2`.

## Stories

| # | Story | Status | Depends on |
|---|---|---|---|
| 15.1 | [Schema + backend extractor + edit endpoints + prompt resolution](./story-15.1.md) | [x] code-complete — awaiting migration run | — |
| 15.2 | [Library seed: model flip + v2 call-topics entry](./story-15.2.md) | [x] done — 2026-05-18 | 15.1 |
| 15.3 | [Call Topics stage UI rewrite (v3 layout + inline edits + selector + popover)](./story-15.3.md) | [x] code-complete — awaiting visual smoke | 15.1, 15.2 |
| 15.4 | [Matching stage read-only display + real-fixture acceptance + rollback regression](./story-15.4.md) | [ ] todo | 15.1, 15.3 |

## Definition of Done
- All 4 stories `[x] done`.
- Real-fixture test (`backend/tests/test_real_fixture_4calls.py`) passes on smoke-test project with 4 FactSet transcripts.
- Rollback regression test passes.
- Manual-test walkthrough completed (see `docs/project/config/2026-05-18-epic-15-manual-tests.md`).
- Per CLAUDE.md mandatory testing rule: real-transcript flow run end-to-end before declaring done.
