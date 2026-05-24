# Active Context — Call Tracker

## Current Story
- **Active epic:** EPIC-18 — Call Topics (v5) + Pass 1 Reliability Rework (code-complete, pending manual smoke test)
- **Branch:** `epic-16-rag-rework` (EPIC-17 v5 and EPIC-18 reliability rework both shipped on this branch)
- **Status:** Code-complete. Migration 034 applied. Awaiting Task 18 smoke test against project B.
- **Last delivered:** Task 20 / STREAM 5 — migration script + runbook (`f755bdf`) — 2026-05-24
- **Next:** User runs Task 18 smoke test (see migration runbook at `docs/project/config/2026-05-24-epic-18-migration-runbook.md`). Re-evaluate P1-RETRIEVAL (S2.4) gating if smoke shows <90% verdicts @ <75% confidence.

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
