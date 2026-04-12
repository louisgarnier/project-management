# Story 5.1 — Artifacts Tab UI

**Epic:** EPIC-5 — Artifacts Stage
**Status:** `done`
**Depends on:** Story 5.2 (Artifact Types API) for live data

---

## Goal
A project-level Artifacts tab (alongside Board and File History in the sidebar) lets the user browse all artifact types for the current project, manage them (create, edit, delete), and import types from other projects. This is the management layer — artifact types defined here are what appear as options during the call workflow.

## Data model note
Artifact types are **project-scoped** — each project has its own list. The 6 defaults are seeded per project at project creation. Importing from another project creates independent copies (no live link between projects).

## Acceptance Criteria

### Viewing
- [x] Artifacts tab accessible from sidebar nav (per-project, same level as Board and File History)
- [x] Page lists all artifact types for the current project: name, description, prompt preview
- [x] Clicking an artifact type expands it to show the full prompt
- [x] Default types (the 6 seeded ones) are visually distinguished (e.g. "Default" badge)

### Creating
- [x] "Add artifact type" button opens a modal with two options: **"Create new"** or **"Import from another project"**
- [x] **Create new:** name + prompt fields → submits `POST /api/projects/{id}/artifact-types` → added to list
- [x] While saving: button shows "Saving…", disabled

### Importing from another project
- [x] **Import from another project:** step 1 — dropdown/list of all other projects
- [x] Step 2 — selecting a project loads that project's artifact types
- [x] User can select one or more types to import (checkboxes)
- [x] Confirming imports creates independent copies in the current project (`POST /api/projects/{id}/artifact-types/import`)
- [x] Imported types appear in the list immediately

### Editing & deleting
- [x] Each artifact type has an edit button — opens inline edit mode for name and prompt
- [x] "Save" confirms edit (`PATCH /api/projects/{project_id}/artifact-types/{id}`)
- [x] Custom types show a delete button — confirmation dialog then `DELETE /api/projects/{project_id}/artifact-types/{id}`
- [x] Default types cannot be deleted (no delete button shown)
- [x] All changes reflected immediately in the list

## Tasks
- [x] Add "Artifacts" nav item to `Sidebar.tsx`
- [x] Create `frontend/app/projects/[id]/artifacts/page.tsx`
- [x] Create `frontend/src/components/ArtifactTypeCard.tsx` — expandable card with prompt, edit, delete
- [x] Create `frontend/src/components/AddArtifactTypeModal.tsx` — two-mode modal: create new OR import from project
- [x] Import flow: project selector → artifact type checklist → confirm
- [x] Add `artifactTypesAPI` to `frontend/src/api/client.ts` (list, create, patch, delete, import)
- [x] Wire delete with confirmation dialog

## Implications for Story 5.2 (Artifact Types API)
- All artifact type endpoints must be scoped to `project_id`: `GET /api/projects/{id}/artifact-types`, etc.
- New endpoint needed: `POST /api/projects/{id}/artifact-types/import` — accepts list of type IDs from another project, creates copies
- 6 defaults seeded per project at project creation time (not global seed)
