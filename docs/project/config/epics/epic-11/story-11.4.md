# Story 11.4 — Frontend Topic Tile Rewrite

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §4.3, §4.5
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Tasks 9–11

---

## Goal
Ship the rich Call Topics tile (Option C) — three colour-coded anchor sections (Decisions / Actions / Open questions), importance dot with rationale tooltip, parked variant, and inline edit mode. Extend TypeScript types and ripple the new fields to the other topic-rendering surfaces.

## Acceptance Criteria
- [ ] `TopicData` TS interface carries `open_questions: string[]`, `is_parked: boolean`, `importance: "high"|"medium"|"low"`, `rationale: string`
- [ ] `LLMProvider` union includes `"openrouter"`
- [ ] `ArtifactType` carries `model: string | null`; `Project` carries `default_model: string | null`
- [ ] `MODEL_RECOMMENDATIONS` constant per `ArtifactCategory` matches spec §4.4.4 table; `PROVIDER_LABELS` exported for UI
- [ ] `CallTopicsStage.TopicRow` renders three colour-coded sections (grey/amber/blue) when populated, hides empty sections, importance dot on left of name with `rationale` tooltip, parked variant (muted border, ⏸ chip, no Actions section, Un-park button)
- [ ] A `SectionBlock` helper handles the three sections' common rendering
- [ ] Edit mode (✎): textareas for summary + each section + status/owner/sentiment/parked controls
- [ ] `TopicEditor`, `TopicsDashboard`, `TopicsPanel`, `TopicEvidenceDrawer` render `open_questions` + surface `is_parked`
- [ ] `tsc --noEmit` clean; `npm run lint` clean

## Tasks
Covers Plan Task 9 (types + constants), Task 10 (tile rewrite), Task 11 (ripple).
