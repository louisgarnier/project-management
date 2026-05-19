# Epic Overview — Call Tracker
> Generated from `docs/project/requirements/5-EPICS.md`
> Stories map to vertical slices in `docs/plans/2026-04-09-call-tracker.md`

| ID | Epic | Status | Stories |
|---|---|---|---|
| EPIC-1 | Foundation & Logging | [x] Done | 3 |
| EPIC-2 | Projects | [x] Done | 3 |
| EPIC-3 | Kanban Board & Calls | [x] Done | 2 |
| EPIC-4 | Transcript Stage | [x] Done | 8 |
| EPIC-5 | Artifacts Stage | [ ] Next | 5 |
| EPIC-6 | Topics Stage | [ ] | 2 |
| EPIC-7 | Two-Step Topic Extraction + New Stages | [ ] | 6 |
| EPIC-8 | Topics Timeline Grid | [ ] | 2 |
| EPIC-9 | M:N Topic Merge + Not-Discussed Verification | [x] Done | 7 |
| EPIC-10 | Topic Lineage + Full-Stage Traceability + Prompt Quality | [x] Done | 9 |
| EPIC-11 | Call Topics Extraction Overhaul (rubric + OpenRouter) | [x] Done | 6 |
| EPIC-12 | Artifacts Overhaul (library + templates + system seed) | [x] Done | 6 |
| EPIC-15 | Call Topics Rebuild — Phase 1 (call_topics) | [x] code-complete | 3 (15.1–15.3) |
| EPIC-15 | Call Topics Rebuild — Phase 2 (artifacts compatibility + xlsx tracker) | [ ] Active | 4 (15.5–15.8) |
| EPIC-15 | Call Topics Rebuild — Phase 3 (matching UI polish + real-fixture + rollback non-reg) | [ ] Deferred | 1 (15.4) + new |

---

## Dependency Order

```
EPIC-1 (Foundation + Logging)
  └─ EPIC-2 (Projects)
       └─ EPIC-3 (Kanban + Calls)
            └─ EPIC-4 (Transcript Stage)
                 └─ EPIC-5 (Artifacts Stage)
                      └─ EPIC-6 (Topics Stage)
                           └─ EPIC-7 (Topic Dashboard)
                                └─ EPIC-8 (Testing + Deployment)
                                     └─ EPIC-9 (M:N Merge + Verification)
                                          └─ EPIC-10 (Lineage + Prompt Traceability)
```

**Rule:** No epic starts until all stories in the previous epic are `[x] Done`.
**Rule:** No feature story starts until Story 1.2 (Logging Foundation) is `[x] Done`.

---

## 🚦 Status

```
Working on : EPIC-15 Phase 2 — Artifacts compatibility + xlsx tracker (branch epic-15-phase-2-artifacts)
Blocked by : —
Next up    : Story 15.5 (call_topics extension: open_questions + decisions + migration 027 + 3-section UI)
Deferred   : Story 15.4 → Phase 3 (matching UI read-only + real-fixture + rollback non-reg test).
             Reason: Call 1 has no matching phase, and tests need a working end-to-end pipeline (Phase 2's job).
```

---

## 📌 Backlog

- [ ] Per-project prompt overrides (US-20 — v2)
- [ ] Export call summary as markdown/PDF (US-22 — v2)
- [ ] Archive / close a project (US-23 — v2)
