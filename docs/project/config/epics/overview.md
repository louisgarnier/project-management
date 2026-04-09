# Epic Overview — Call Tracker
> Generated from `docs/project/requirements/5-EPICS.md`
> Stories map to vertical slices in `docs/plans/2026-04-09-call-tracker.md`

| ID | Epic | Status | Stories |
|---|---|---|---|
| EPIC-1 | Foundation & Logging | [x] Done | 3 |
| EPIC-2 | Projects | [x] Done | 3 |
| EPIC-3 | Kanban Board & Calls | [x] Done | 2 |
| EPIC-4 | Transcript Stage | [ ] | 4 |
| EPIC-5 | Artifacts Stage | [ ] | 4 |
| EPIC-6 | Topics Stage | [ ] | 2 |
| EPIC-7 | Topic Dashboard | [ ] | 2 |
| EPIC-8 | Testing & Deployment | [ ] | 2 |

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
```

**Rule:** No epic starts until all stories in the previous epic are `[x] Done`.
**Rule:** No feature story starts until Story 1.2 (Logging Foundation) is `[x] Done`.

---

## 🚦 Status

```
Working on : EPIC-4 — Transcript Stage (Story 4.4)
Blocked by : —
Next up    : EPIC-4 / Story 4.4
```

---

## 📌 Backlog

- [ ] Per-project prompt overrides (US-20 — v2)
- [ ] Export call summary as markdown/PDF (US-22 — v2)
- [ ] Archive / close a project (US-23 — v2)
