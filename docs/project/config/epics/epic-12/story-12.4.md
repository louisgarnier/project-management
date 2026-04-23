# Story 12.4 — Frontend Two-Tier Layout + Card Per Kind

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** pending
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §4.9, §4.10, §4.11, §4.12
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Tasks 8–10

## Goal
Extend frontend types + add cost estimation. Split the Artifacts page into labeled Tier 1 / Tier 2 sections and fix the workflow prompts filter so `merge_verification` + `not_discussed_check` are no longer hidden. Rework `ArtifactTypeCard` to render differently per `kind` (template = description + Preview; hybrid = intro/closing prompts; llm = existing).

## Acceptance Criteria
- [ ] `ArtifactKind` + `LibraryEntry` TS types defined
- [ ] `ArtifactType` TS type grows `kind`, `template_id`, `library_ref_id`
- [ ] `MODEL_COSTS` map + `estimateCost(slug)` helper exported from `@/constants/models`
- [ ] Artifacts page filter includes `merge_verification` + `not_discussed_check` (fixes hidden workflow prompts)
- [ ] Artifacts page has two labeled sections (Tier 1 ⚙️ + Tier 2 📝) with descriptions
- [ ] "+ Add artifact type" button only appears in Tier 2 section header
- [ ] `ArtifactTypeCard` renders different body per `kind`:
  - template: description + Preview button (no prompt/provider controls) + "Cost: $0 (template)"
  - hybrid: template description + two prompt fields (intro/closing) + shared provider/model
  - llm: existing card + diff-vs-canonical badge + cost preview + Publish-to-library button
- [ ] Diff-vs-canonical badge (`⟲ canonical` / `✎ edited`) fetched via GET `library-source` on mount
- [ ] `tsc --noEmit` + `npm run lint` clean

## Tasks
Covers Plan Task 8 (types + constants), Task 9 (page layout), Task 10 (card per kind).
