# Active Context — Call Tracker

## Current Story
- **Active epic:** EPIC-15 — Call Topics Rebuild (Phase 2 — Artifacts Rebuild + xlsx Tracker)
- **Branch:** `epic-15-phase-2-artifacts` (Phase 1 stories 15.1–15.4 baseline; Phase 2 stories 15.5–15.8 land on this branch)
- **Status:** Phase 2 stories scoped (4 files written 2026-05-19) — ready to build
- **Phase 1 docs:** brainstorm + PRD + architecture all locked (`docs/project/config/2026-05-18-epic-15-call-topics-rebuild-*.md`)
- **Phase 2 docs:** brainstorm + PRD + architecture all locked (`docs/project/config/2026-05-18-epic-15-phase-2-*.md`)
- **Mockups:** `call-topic-tile-v3.html` (Phase 1), `phase2-call-topics-extended.html`, `phase2-project-tracker-tab-v3.html` (Phase 2, both approved 2026-05-18)
- **Next:** Story 15.5 (P2-A — call_topics extension: open_questions + decisions + migration 027 + 3-section UI)
- **Last delivered:** Story 15.3 — Call Topics stage UI rewrite (v3 flat-table, repeated topic+chips, inline edits, evidence popover, prompt selector); legacy TopicEditor + EvidenceDrawer deleted (2026-05-18)

### EPIC-15 Phase 1 (baseline)
| # | Story | Status | Depends on |
|---|---|---|---|
| 15.1 | Schema + backend extractor + edit endpoints + prompt resolution | [x] code-complete — awaiting migration run | — |
| 15.2 | Library seed: model flip + v2 call-topics entry | [x] done — 2026-05-18 | 15.1 |
| 15.3 | Call Topics stage UI rewrite (v3 layout + inline edits) | [x] code-complete — awaiting visual smoke | 15.1, 15.2 |
| 15.4 | Matching read-only display + real-fixture + rollback regression | [ ] DEFERRED → Phase 3 (2026-05-19) | 15.1, 15.3, Phase 2 closed |

### EPIC-15 Phase 2 (active)
| # | Story | Workstream | Status | Depends on |
|---|---|---|---|---|
| 15.5 | Call-topics extension: open_questions + decisions | P2-A | [ ] todo | — |
| 15.6 | `context_scope` 4-value enum + context-assembly seam | P2-B | [ ] todo | — (parallel-safe) |
| 15.7 | Per-item lifecycle + chronology + RAG verification + accumulator | P2-C | [ ] todo | 15.5, 15.6 |
| 15.8 | xlsx tracker exporter + ProjectTrackerTab + smoke acceptance | P2-D | [ ] todo | 15.7 |

**Dependency order:** 15.5 → 15.7 → 15.8 sequential; 15.6 parallel.

### EPIC-15 Phase 3 (deferred — opens after Phase 2 closes)
| # | Story | Notes |
|---|---|---|
| 15.4 | Matching UI read-only display (key_terms + evidence popover + tasks) on `ProjectMatchingStage` / `TopicsDashboard` / `TopicsPanel` / `ProjectUpdatesStage` | Deferred 2026-05-19 — Call 1 has no matching phase, so doesn't block Phase 2. |
| 15.4 | Real-fixture acceptance test (`backend/tests/test_real_fixture_4calls.py`) running the 4 FactSet transcripts end-to-end on smoke-test project `17e2687f-bdd8-43ee-88a7-d2bd79a13925` | Deferred 2026-05-19 — needs working end-to-end pipeline (Phase 2 delivers). |
| 15.4 | Rollback regression test: re-extract Call 2, assert Calls 3+4 roll back to call_topics stage | Deferred 2026-05-19 — behaviour works today (user confirmed), formal non-reg test deferred. **User flagged non-regression coverage as KEY for Phase 3.** |
| 15.4 | Manual-test doc `docs/project/config/2026-05-18-epic-15-manual-tests.md` covering all 4 calls end-to-end | Deferred 2026-05-19 — written after Phase 2 stabilises. |

**Phase 3 entry condition:** Phase 2 stories 15.5–15.8 all `[x] done` AND Call 1 artifacts smoke-test clean.

### EPIC-12 Stories (last delivered — for reference)
| # | Story | Status |
|---|---|---|
| 12.1 | Schema + template renderers | done 2026-04-23 |
| 12.2 | Artifact library (seed + CRUD API) | done 2026-04-23 |
| 12.3 | Artifact types API + generation fork | done 2026-04-23 |
| 12.4 | Frontend two-tier layout + card per kind | done 2026-04-23 |
| 12.5 | Library modal + /library page + publish dialog | done 2026-04-23 |
| 12.6 | End-to-end smoke + close | done 2026-04-23 |

### EPIC-11 (previous, code complete pending validation)
- **Epic:** EPIC-11 — Call Topics Extraction Overhaul — **code complete 2026-04-22 (pending manual validation)**
- **Branch:** `epic-11-call-topics-overhaul`
- **Manual tests:** `docs/project/config/2026-04-22-epic-11-manual-tests.md`

### EPIC-11 Stories
| # | Story | Status |
|---|---|---|
| 11.1 | Schema & Prompt Foundation | done 2026-04-22 |
| 11.2 | Prompt Lifecycle | done 2026-04-22 |
| 11.3 | OpenRouter Provider + Model Propagation | done 2026-04-22 |
| 11.4 | Frontend Topic Tile Rewrite | done 2026-04-22 |
| 11.5 | Artifact Type Card + Project Settings | done 2026-04-22 |
| 11.6 | End-to-end Validation + Close | done 2026-04-22 |

### EPIC-10 (previous)
- **Epic:** EPIC-10 — Topic Lineage + Full-Stage Traceability + Prompt Quality — **DONE 2026-04-21**
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
