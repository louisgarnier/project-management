# Active Context — Call Tracker

## Current Story
- **Active epic:** EPIC-19 — Task-level project matching + narrowed 3-pass synthesis (code-complete, pending smoke test)
- **Branch:** `epic-16-rag-rework`
- **Status:** All 15 tasks landed (commits ca799cd → final wrap-up). Migration 035 pending manual apply in Supabase Dashboard. Backfill script ready.
- **Next:** Run manual steps per `docs/project/config/2026-05-25-epic-19-migration-runbook.md`, then smoke test project a / call b end-to-end under the new pipeline.

## EPIC-19 design + plan + brainstorm
- Brainstorm: `docs/project/config/2026-05-25-epic-19-brainstorm.md`
- Plan: `docs/project/config/2026-05-25-epic-19-implementation-plan.md`
- Migration runbook: `docs/project/config/2026-05-25-epic-19-migration-runbook.md`

## Prior epic state
- **EPIC-18** (topic-level Pass 1/2/3 reliability): code-complete, smoke revealed deeper architectural issue → EPIC-19 reframe

## What EPIC-18 left behind that EPIC-19 inherits
- ✅ Foundation kept: unified `project_topic_state` view (ADR-003), line-number citation pattern (ADR-004), V5-CORE structured registry, Pass 1 fixtures, verification-asymmetry UX, migration script
- ❌ To be obsoleted in EPIC-19: `run_verify_new` (topic-level), `run_verify_canonical_match`, rarity check, sanity flag stack, `verify_new_topic.py` prompt

## Prior epic
- **EPIC-17 / v5 pipeline:** shipped (11 commits, see git log)
- **EPIC-15 Phase 2:** dropped 2026-05-20 (chronology rewrites failed twice)
- **EPIC-15 Phase 1 + Story 15.5:** stable

## What was dropped (2026-05-20)
EPIC-15 Phase 2 stories 15.6 / 15.7 / 15.8 were rolled back: the `context_scope` 4-value enum, the chronology service + RAG audit + accumulator, the xlsx tracker exporter, and the Project Tracker UI tab. Two attempted rewrites of the chronology pipeline (2-LLM-pass and 1-LLM-pass-with-citations) did not produce coherent cross-call updates on real data. Archive of the dropped work lives in `../archive/epic-15-phase-2-DROPPED/`.

DB migrations 027 (Story 15.5 — applied) and 028/029 (Phase 2 — applied) remain in Supabase. Their columns/constraints are now unused by the rolled-back code but cause no breakage. Drop them manually if a clean schema is desired.

## What was dropped (2026-05-20)
EPIC-15 Phase 2 stories 15.6 / 15.7 / 15.8 were rolled back: the `context_scope` 4-value enum, the chronology service + RAG audit + accumulator, the xlsx tracker exporter, and the Project Tracker UI tab. Two attempted rewrites of the chronology pipeline (2-LLM-pass and 1-LLM-pass-with-citations) did not produce coherent cross-call updates on real data. Archive of the dropped work lives in `../archive/epic-15-phase-2-DROPPED/`.

DB migrations 027 (Story 15.5 — applied) and 028/029 (Phase 2 — applied) remain in Supabase. Their columns/constraints are now unused by the rolled-back code but cause no breakage. Drop them manually if a clean schema is desired.

## Completed Epics
See `overview.md` for the full index. All completed epics' plans + designs + story files live in `../archive/<epic-folder>/`.
