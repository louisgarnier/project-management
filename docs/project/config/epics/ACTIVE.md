# Active Context — Call Tracker

## Current Story
- **Epic:** EPIC-10 — Topic Lineage + Full-Stage Traceability + Prompt Quality — **DONE 2026-04-21**
- **Next:** TBD — all 9 stories complete.
- **Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` + `docs/project/config/2026-04-21-story-10.9-timeline-provenance-design.md`
- **PRD:** `docs/project/config/prd-epic10-topic-lineage-and-prompt-traceability.md`

### EPIC-10 Stories
| # | Story | Status | Depends on |
|---|---|---|---|
| 10.1 | Lineage Helper + Merge-Prompt Fix | **done 2026-04-20** | — |
| 10.2 | Prompts Audit (Read-Only Documentation) | **done 2026-04-21** | 10.1 |
| 10.3 | Topic Evidence API | **done 2026-04-21** | 10.1 |
| 10.4 | Evidence Drawer UI — Lineage Mode | **done 2026-04-21** | 10.3 |
| 10.5 | "+ new (merged)" Label on Timeline Cells | **done 2026-04-21** | 10.3 |
| 10.6 | Implement Prompt Fixes From Audit | **done 2026-04-21** | 10.2 |
| 10.7 | Call Topics Stage: Evidence Drawer | **done 2026-04-21** | 10.4 |
| 10.8 | Project Matching Stage: Side-by-Side Evidence Drawer | **done 2026-04-21** | 10.3, 10.4 |
| 10.9 | Timeline Item Provenance + Ancestor Visualization | **done 2026-04-21** | 10.1, 10.3, 10.4, 10.5 |

### Side fix
- **ERR-004** — Promote-not-discussed state lost on re-merge/refresh — **done 2026-04-21** (commit `d6773de`)

### EPIC-9 Stories (Done)
| # | Story | Status |
|---|---|---|
| 9.1 | DB Migration: M:N Merge + Verification Schema | done |
| 9.2 | Transcript Excerpt Capture in Extraction | done |
| 9.3 | M:N ProjectMatchingStage UI | done |
| 9.4 | M:N Merge Pipeline + RAG Synthesis Backend | done |
| 9.5 | Not-Discussed Verification Backend + UI | done |
| 9.6 | Timeline: Merged Cell Type + Archive Filter | done |
| 9.7 | Rollback Updates + Integration Testing | done |

## Completed
- [x] EPIC-1 / Story 1.1 — Repo Scaffold & Environment — 2026-04-09
- [x] EPIC-1 / Story 1.2 — Logging Foundation — 2026-04-09
- [x] EPIC-1 / Story 1.3 — Supabase Schema — 2026-04-09
- [x] EPIC-2 / Story 2.1 — Projects API — 2026-04-09
- [x] EPIC-2 / Story 2.2 — Project List UI — 2026-04-09 (superseded by 2.3)
- [x] EPIC-2 / Story 2.3 — App Shell & Project List UI (Redesign) — 2026-04-09
- [x] EPIC-3 / Story 3.1 — Calls API with Sequential Enforcement — 2026-04-09
- [x] EPIC-3 / Story 3.2 — Kanban Board UI — 2026-04-09
- [x] EPIC-4 / Story 4.1 — Local Transcription Server — 2026-04-09
- [x] EPIC-4 / Story 4.2 — Transcript Stage Backend — 2026-04-09
- [x] EPIC-4 / Story 4.3 — Transcript Stage UI — 2026-04-09
- [x] EPIC-4 / Story 4.4 — Server Control UI — 2026-04-09
- [x] EPIC-4 / extras — Transcription engine fixes, transcript review, Metal warmup — 2026-04-10
- [x] EPIC-4 / Story 4.5 — Transcript Review, Edit & Download — 2026-04-10
- [x] EPIC-4 / Story 4.6 — Context File Attachments — 2026-04-10
- [x] EPIC-4 / Story 4.7 — Replace Transcription Engine with MLX Whisper — 2026-04-10
- [x] EPIC-4 / Story 4.8 — Kanban History Trail + Persistent Transcript Panel — 2026-04-10
- [x] EPIC-5 / Story 5.1 — Artifacts Tab UI — 2026-04-12
- [x] EPIC-5 / Story 5.2 — Artifact Types API — 2026-04-12
- [x] EPIC-5 / Story 5.3 — Claude Service & SSE — 2026-04-12
- [x] EPIC-5 / Story 5.4 — Artifacts Stage UI — 2026-04-12
- [x] EPIC-5 / Story 5.5 — Kanban Row-Per-Call Redesign — 2026-04-13
- [x] EPIC-6 / Story 6.1 — Topics API (backend) — 2026-04-13
- [x] EPIC-6 / Story 6.2 — Topics UI (frontend) — 2026-04-13
- [x] EPIC-7 / Story 7.1 — DB Migration: New Kanban Stages — 2026-04-14
- [x] EPIC-7 / Story 7.2 — Step 1: Call Topics Extraction Endpoint — 2026-04-14
- [x] EPIC-7 / Story 7.3 — Step 2: Aggregate Endpoint — 2026-04-14
- [x] EPIC-7 / Story 7.4 — Call Topics UI — 2026-04-14
- [x] EPIC-7 / Story 7.5 — Project Matching + Project Updates UI (2 stages) — 2026-04-14
- [x] EPIC-7 / Story 7.6 — Artifact Context: Inject Project Topics — 2026-04-14
