# Story 15.8 — xlsx Tracker Exporter + ProjectTrackerTab + Smoke Acceptance

**Epic:** EPIC-15 — Call Topics Rebuild (Phase 2 / P2-D)
**Status:** [ ] todo
**Spec:** `docs/project/config/2026-05-18-epic-15-phase-2-architecture.md` §4.1 (exporter), §4.2 (tab), §5 (endpoint), §8 (perf budget), §10 (openpyxl gotchas)
**PRD:** `docs/project/config/2026-05-18-epic-15-phase-2-prd.md` G9, G10, G11, US-P2-06, US-P2-07, US-P2-08, US-P2-09, FR-P2-10/11/12, NFR-P2-01, NG2, NG3, Q3, Q5
**Approved mockups:** `phase2-project-tracker-tab-v3.html` (5 sub-views with ⓘ popovers, default Dashboard)
**Blocks:** — (closes EPIC-15 Phase 2)
**Depends on:** 15.7 (chronology + lifecycle metadata must be populated to render meaningful cells)

## Goal
Ship the xlsx tracker exporter (5 sheets, openpyxl) and the Project Tracker sub-tab inside the Artifacts page (5 sub-views per the approved v3 mockup). Add `GET /api/projects/{id}/export.xlsx` as a streaming binary download. Pass real-fixture smoke on the 4-call FactSet project: render 5 sub-views in the UI, export the xlsx, open in Excel + Google Sheets without breakage.

## Acceptance Criteria

### Backend — xlsx exporter
- [ ] `backend/exporters/xlsx_tracker.py` — NEW:
  - [ ] Single public function: `def build_tracker_xlsx(project_id: str) -> bytes`.
  - [ ] Renders **5 sheets** named exactly as v04:
    1. `Dashboard` — high-level counts (topics, open OQs, decisions, tasks by status), per architecture §4.1.
    2. `Chronology` — 1 row per topic × 1 column per call date + a final `RAG note` column. Each cell = `topic_updates.chronology_narrative`.
    3. `Anchors lifecycle` — 1 row per item (task / open_question) with columns: topic, item text, owner, status, added_in_call (date), closed_in_call (date / blank).
    4. `Decisions log` — 1 row per decision: topic, text, decided_in_call (date).
    5. `Key terms registry` — 1 row per (topic, key_term) pair, with first-seen call date.
  - [ ] Reads from `list_project_topics(project_id)` + `list_topics_timeline(project_id)` (existing helpers); no new SQL.
  - [ ] Header row: bold + frozen via `ws.freeze_panes = "A2"`. Column widths tuned per sheet (chronology cells wider; status / date columns narrower).
  - [ ] Multi-line cells: `Alignment(wrap_text=True)` per §10.
  - [ ] **No charts, no conditional formatting, no pivots** (NG3).
  - [ ] Streams via `BytesIO` → `workbook.save(stream)` → `stream.getvalue()`. No disk writes.

### Backend — endpoint
- [ ] `backend/routers/projects.py` (or existing): `GET /api/projects/{project_id}/export.xlsx`:
  - [ ] Returns `StreamingResponse` over the bytes from `build_tracker_xlsx`.
  - [ ] `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
  - [ ] `Content-Disposition: attachment; filename="<slug>-tracker-<ISO_date>.xlsx"` where slug = `_slugify(project.name)` (existing helper in `backend/services/export_service.py`) and date = today (UTC, ISO `YYYY-MM-DD`) per Q5.
  - [ ] 404 if project not found.
  - [ ] Performance budget: < 30s for a 50-topic × 20-call project (NFR-P2-01).

### Frontend — types
- [ ] `frontend/src/types/index.ts`: confirm `TopicData.chronology_narrative` + `TopicData.rag_verification_note` exposed (added in 15.5/15.7).

### Frontend — ProjectTrackerTab
- [ ] `frontend/src/components/ProjectTrackerTab.tsx` — NEW:
  - [ ] Renders **5 sub-views** matching the xlsx sheets: Dashboard, Chronology, Anchors lifecycle, Decisions log, Key terms registry. Per approved mockup `phase2-project-tracker-tab-v3.html`.
  - [ ] Each sub-view has a header with an ⓘ popover next to the sub-view name explaining what the view shows (info text per mockup v3).
  - [ ] Default sub-view: **Dashboard** (Q3). URL hash `#dashboard`; switchable via `#chronology`, `#anchors`, `#decisions`, `#key-terms`. Reading the hash on mount selects the right view; clicking a tab updates the hash.
  - [ ] Top-right **Export-to-xlsx** button → calls `GET /api/projects/{id}/export.xlsx`; uses the proxied route via Next.js (`/api/proxy/projects/{id}/export.xlsx`) to stay same-origin; browser triggers download.
  - [ ] Loading + error states per sub-view; "no topics yet" empty state when project has zero topics.
- [ ] `frontend/src/components/tracker/` (subdirectory) — one file per sub-view component if size warrants (`DashboardView.tsx`, `ChronologyView.tsx`, `AnchorsLifecycleView.tsx`, `DecisionsLogView.tsx`, `KeyTermsRegistryView.tsx`). Reads via existing project-topics API.

### Frontend — Artifacts page sub-tab nav
- [ ] `frontend/app/projects/[id]/artifacts/page.tsx`:
  - [ ] Add top-level 2-sub-tab nav: **"Generate artifacts"** (existing flow, unchanged) | **"Project tracker"** (new `ProjectTrackerTab`).
  - [ ] Default tab: Generate artifacts (preserves current UX).

### Frontend — proxy
- [ ] `frontend/app/api/proxy/[...path]/route.ts` — already handles binary passthrough for files (EPIC-4 / Story 4.6 precedent); verify xlsx mime type passes through unchanged. Add a regression test snippet if not covered.

### Tests
- [ ] Backend `backend/tests/test_xlsx_tracker.py` — NEW:
  - [ ] Smoke: `build_tracker_xlsx` for a fixture project produces a `.xlsx` byte stream that re-opens via `openpyxl.load_workbook(BytesIO(bytes))` and has 5 sheets with the exact expected names.
  - [ ] Chronology sheet row count = topic count; column count = call count + 1 (RAG note).
  - [ ] Anchors lifecycle includes both tasks and open_questions; closed_in_call_id renders as date or blank.
  - [ ] Decisions log row count = sum of `decisions[]` across all topics.
  - [ ] 404 path: missing project → `build_tracker_xlsx` raises; router returns 404.
- [ ] Frontend: `tsc --noEmit` + `eslint` clean.
- [ ] **Real-fixture smoke** (Definition of Done):
  - [ ] On the 4-call FactSet smoke-test project, generate xlsx, open in Excel + Google Sheets, confirm no rendering breakage (§7 manual validation gate).
  - [ ] Render all 5 sub-views in the UI on the same project, confirm hash routing + popovers work.
  - [ ] Export button triggers download with the expected filename pattern `factset-swib-tracker-2026-MM-DD.xlsx`.

## Out of scope (per PRD non-goals)
- Round-trip editing of xlsx (NG2 — read-only export).
- Charts / conditional formatting / pivots in xlsx (NG3).
- Re-trigger button for stale chronology rows → deferred (manual re-trigger via SQL, documented in architecture §9).
- Custom report builder UI → not in Phase 2 scope.

## Notes
- The xlsx exporter is **pure-Python in-process** — no Celery, no background worker. Performance budget §8: 50 topics × 20 calls → ~5–15s render; within NFR-P2-01's 30s SLA.
- Hash routing inside ProjectTrackerTab does **not** affect Next.js routing; it's a pure client-side `useEffect(window.location.hash, ...)` pattern, same approach as the board page tab query param in 6.2.
- The Dashboard sub-view counts must match the underlying sheets (single source of truth = `list_project_topics`); duplication via a separate aggregation query is forbidden.
