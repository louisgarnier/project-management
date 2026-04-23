# Story 12.1 — Schema + Template Renderers

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** pending
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §4.1–4.4
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Tasks 1–2

## Goal
Lay the foundation: DB migration 021 introduces `kind`, `template_id`, `library_ref_id` columns on `artifact_types` + creates the new `artifact_library` table with FK. Five pure-Python template renderers + a registry implement the zero-LLM artifact kind.

## Acceptance Criteria
- [ ] Migration 021 adds 3 columns to `artifact_types` + creates `artifact_library` table (11 columns, unique name, kind CHECK)
- [ ] `artifact_types_library_ref_fkey` FK constraint (ON DELETE SET NULL) wires rows back to library
- [ ] `backend/templates/` package with 5 renderer modules: `next_steps.py`, `questions_list.py`, `agenda_skeleton.py`, `risk_register.py`, `decisions_digest.py`
- [ ] `backend/templates/registry.py` maps the 5 `template_id` keys to render functions
- [ ] Each renderer accepts `topics: list[dict]` + optional `scope: str` and returns a markdown string
- [ ] Owner-prefix detection in `next_steps` bolds `Nick: foo` as `**Nick:** foo`
- [ ] `agenda_skeleton` filters out resolved topics and sorts concern-first
- [ ] `risk_register` only includes topics where `sentiment=concern` OR `is_parked=true`
- [ ] `decisions_digest` flattens all decisions across topics grouped by topic
- [ ] 9 unit tests cover rendering logic and edge cases

## Tasks
Covers Plan Task 1 (migration 021), Task 2 (5 template renderers + registry + tests).
