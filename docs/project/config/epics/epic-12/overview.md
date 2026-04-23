# Epic 12 — Artifacts Overhaul

**Status:** in progress — started 2026-04-23
**Spec:** [`2026-04-23-epic-12-artifacts-overhaul-design.md`](../../2026-04-23-epic-12-artifacts-overhaul-design.md)
**Plan:** [`2026-04-23-epic-12-artifacts-overhaul-plan.md`](../../2026-04-23-epic-12-artifacts-overhaul-plan.md)
**Branch:** `epic-12-artifacts-overhaul`

## Why
Artifacts today are LLM-only, auto-seeded as 6 per project, and two of the four workflow prompts are invisible (filter bug in `/projects/{id}/artifacts`). EPIC-12 introduces (a) three artifact kinds so templates + hybrids replace re-extraction waste; (b) a shared `artifact_library` with publish-from-project flow; (c) a two-tier page layout surfacing all 4 workflow prompts; (d) per-type reset-to-default that works on every artifact type.

## Stories
| # | Story | Status |
|---|---|---|
| 12.1 | Schema + template renderers | pending |
| 12.2 | Artifact library (seed + CRUD API) | pending |
| 12.3 | Artifact types API extensions + generation fork | pending |
| 12.4 | Frontend two-tier layout + card per kind | pending |
| 12.5 | Library modal + /library page + publish dialog | pending |
| 12.6 | End-to-end smoke + close | pending |
