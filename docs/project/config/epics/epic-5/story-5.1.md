# Story 5.1 — Artifacts Tab UI

**Epic:** EPIC-5 — Artifacts Stage
**Status:** `pending`
**Depends on:** Story 5.2 (Artifact Types API) for live data

---

## Goal
A project-level Artifacts tab (alongside Board and File History in the sidebar) lets the user browse all artifact types for the current project, manage them (create, edit, delete), and import types from other projects. This is the management layer — artifact types defined here are what appear as options during the call workflow.

## Data model note
Artifact types are **project-scoped** — each project has its own list. The 6 defaults are seeded per project at project creation. Importing from another project creates independent copies (no live link between projects).

## Acceptance Criteria

### Viewing
- [ ] Artifacts tab accessible from sidebar nav (per-project, same level as Board and File History)
- [ ] Page lists all artifact types for the current project: name, description, prompt preview
- [ ] Clicking an artifact type expands it to show the full prompt
- [ ] Default types (the 6 seeded ones) are visually distinguished (e.g. "Default" badge)

### Creating
- [ ] "Add artifact type" button opens a modal with two options: **"Create new"** or **"Import from another project"**
- [ ] **Create new:** name + prompt fields → submits `POST /api/projects/{id}/artifact-types` → added to list
- [ ] While saving: button shows "Saving…", disabled

### Importing from another project
- [ ] **Import from another project:** step 1 — dropdown/list of all other projects
- [ ] Step 2 — selecting a project loads that project's artifact types
- [ ] User can select one or more types to import (checkboxes)
- [ ] Confirming imports creates independent copies in the current project (`POST /api/projects/{id}/artifact-types/import`)
- [ ] Imported types appear in the list immediately

### Editing & deleting
- [ ] Each artifact type has an edit button — opens inline edit mode for name and prompt
- [ ] "Save" confirms edit (`PATCH /api/projects/{project_id}/artifact-types/{id}`)
- [ ] Custom types show a delete button — confirmation dialog then `DELETE /api/projects/{project_id}/artifact-types/{id}`
- [ ] Default types cannot be deleted (no delete button shown)
- [ ] All changes reflected immediately in the list

## Tasks
- [ ] Add "Artifacts" nav item to `Sidebar.tsx`
- [ ] Create `frontend/app/projects/[id]/artifacts/page.tsx`
- [ ] Create `frontend/src/components/ArtifactTypeCard.tsx` — expandable card with prompt, edit, delete
- [ ] Create `frontend/src/components/AddArtifactTypeModal.tsx` — two-mode modal: create new OR import from project
- [ ] Import flow: project selector → artifact type checklist → confirm
- [ ] Add `artifactTypesAPI` to `frontend/src/api/client.ts` (list, create, patch, delete, import)
- [ ] Wire delete with confirmation dialog

## Implications for Story 5.2 (Artifact Types API)
- All artifact type endpoints must be scoped to `project_id`: `GET /api/projects/{id}/artifact-types`, etc.
- New endpoint needed: `POST /api/projects/{id}/artifact-types/import` — accepts list of type IDs from another project, creates copies
- 6 defaults seeded per project at project creation time (not global seed)
