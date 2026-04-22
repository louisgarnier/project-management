# Epic 11 — Call Topics Extraction Overhaul

**Status:** in progress — started 2026-04-22
**Spec:** [`2026-04-22-call-topics-extraction-overhaul-design.md`](../../2026-04-22-call-topics-extraction-overhaul-design.md)
**Plan:** [`2026-04-22-call-topics-extraction-overhaul-plan.md`](../../2026-04-22-call-topics-extraction-overhaul-plan.md)
**Branch:** `epic-11-call-topics-overhaul`

## Why
Call topic extraction produces fragmented, low-confidence, thin-summary output that the user doesn't trust. The tile shows too little to judge quality. No signal flows from project-level context into extraction. The prompt literally says *"do not merge separate topics into one"* — causing the fragmentation. This epic rewrites the prompt around a 3-of-4 rubric, introduces three distinct anchor types (decisions / actions / open questions), enriches the tile with inline sections + importance dot, and integrates OpenRouter so the user can pick the best model per prompt.

## Stories

| # | Story | Status |
|---|---|---|
| 11.1 | Schema & Prompt Foundation (Tasks 1–3) | in_progress |
| 11.2 | Prompt Lifecycle (Tasks 4–6) | pending |
| 11.3 | OpenRouter Provider + Model Propagation (Tasks 7–8) | pending |
| 11.4 | Frontend Topic Tile Rewrite (Tasks 9–11) | pending |
| 11.5 | Artifact Type Card + Project Settings (Tasks 12–13) | pending |
| 11.6 | End-to-end Validation + Close (Task 14) | pending |

Each story groups 1–3 tasks from the implementation plan. Stories close sequentially.
