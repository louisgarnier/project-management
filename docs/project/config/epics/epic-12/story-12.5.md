# Story 12.5 — Library Modal + /library Page + Publish Dialog

**Epic:** EPIC-12 — Artifacts Overhaul
**Status:** done — 2026-04-23
**Spec:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-design.md` §4.8, §4.13, §4.14
**Plan:** `docs/project/config/2026-04-23-epic-12-artifacts-overhaul-plan.md` Tasks 11–13

## Goal
Expand `AddArtifactTypeModal` with a 3rd "Browse library" tab (new default). Build `/library` top-level page with system/yours sections, edit/delete/reset-system controls, and an `LibraryEntryCard` component. Build `PublishToLibraryDialog` wired into `ArtifactTypeCard`.

## Acceptance Criteria
- [x] `libraryAPI` methods added to `api/client.ts` (list, create, update, delete, resetSystem)
- [x] `artifactTypesAPI.fromLibrary(projectId, libraryId)` added
- [x] `AddArtifactTypeModal` has 3 tabs: Browse library (default), Create new, Import from another project
- [x] Browse library tab filters out entries already present via `library_ref_id` match
- [x] Library entry rows show kind icon, system/user badge, Add button
- [x] `/library` top-level page with System / Yours sections
- [x] `LibraryEntryCard` supports edit inline (name, description, prompt for LLM, model, seeded-toggle), delete (non-system only)
- [x] "Reset system to defaults" button with confirmation
- [x] `PublishToLibraryDialog` takes an `ArtifactType`, posts to `/api/artifact-types/{id}/publish-to-library` with `{name, description}`
- [x] Publish button wired into `ArtifactTypeCard` — hidden for templates/hybrids and already-library-linked types
- [x] Sidebar gains "📚 Artifact Library" nav link to `/library`
- [x] `tsc --noEmit` + `npm run lint` clean

## Tasks
Covers Plan Task 11 (library modal tab), Task 12 (/library page + LibraryEntryCard + sidebar), Task 13 (publish dialog).
