# Active Context — Call Tracker

## Current Story
- **Active epic:** EPIC-19 — Task-level Pass 1 redesign (to be brainstormed)
- **Branch:** `epic-16-rag-rework`
- **Status:** EPIC-18 shipped 2026-05-24. Task 18 smoke test on project 'a' call b (2026-05-25) exposed systemic confidence inflation from topic-level rarity/sanity penalty stack (18-30% confidence on semantically-correct merges). D5 gate triggered. Decision: skip the planned S2.4 P1-RETRIEVAL fallback; pivot to EPIC-19 task-level redesign instead.
- **EPIC-18 smoke findings:** verdicts semantically correct on project 'a' (5 merges + 2 truly_new), but workflow forces manual review on all because S07/Meeting logistics fail rarity check (common-term topics), Risk model arch hit insufficient_verdict_citations. S2.2 canonical-match path never triggers in real usage because `topic_match_groups.project_topic_ids` is empty (project_matching is a passthrough). See `workflow/ERRORS.md` ERR-007 for the one real bug fixed mid-flight.
- **Next:** Brainstorm EPIC-19 (task-level matching, deterministic pre-match → semantic for unmatched, derived topic verdict). See [[project_epic_19_task_level_redesign]] memory.

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
