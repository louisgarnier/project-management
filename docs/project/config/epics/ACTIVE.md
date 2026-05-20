# Active Context — Call Tracker

## Current Story
- **Active epic:** none
- **Branch:** `epic-15-phase-2-artifacts` — rolled back 2026-05-20 to `8169f21` (end of Story 15.5)
- **Status:** Stable. Phase 1 done, Story 15.5 done, Phase 2 dropped.
- **Last delivered:** Story 15.5 — Call Topics extension (open_questions + decisions, 3-section UI, migration 027) — 2026-05-19

## What was dropped (2026-05-20)
EPIC-15 Phase 2 stories 15.6 / 15.7 / 15.8 were rolled back: the `context_scope` 4-value enum, the chronology service + RAG audit + accumulator, the xlsx tracker exporter, and the Project Tracker UI tab. Two attempted rewrites of the chronology pipeline (2-LLM-pass and 1-LLM-pass-with-citations) did not produce coherent cross-call updates on real data. Archive of the dropped work lives in `../archive/epic-15-phase-2-DROPPED/`.

DB migrations 027 (Story 15.5 — applied) and 028/029 (Phase 2 — applied) remain in Supabase. Their columns/constraints are now unused by the rolled-back code but cause no breakage. Drop them manually if a clean schema is desired.

## Completed Epics
See `overview.md` for the full index. All completed epics' plans + designs + story files live in `../archive/<epic-folder>/`.
