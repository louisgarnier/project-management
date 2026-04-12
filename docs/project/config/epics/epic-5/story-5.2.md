# Story 5.2 — Artifacts Tab UI

**Epic:** EPIC-5 — Artifacts Stage
**Status:** `pending`
**Depends on:** Story 5.1

---

## Goal
A project-level Artifacts tab (alongside Board and Topics in the sidebar) lets the user browse all artifact types, read their prompts, create custom types, and delete custom ones. This is the management layer — artifact types defined here are what appear as options during the call workflow.

## Acceptance Criteria
- [ ] Artifacts tab accessible from sidebar nav (per-project, same level as Board and File History)
- [ ] Page lists all artifact types: name, description of what it does, prompt preview
- [ ] Clicking an artifact type expands it to show the full prompt
- [ ] "New artifact type" button opens a form: name + prompt fields
- [ ] Submitting creates a new custom artifact type (calls `POST /api/artifact-types`)
- [ ] Custom types show a delete button — clicking prompts confirmation then deletes (calls `DELETE /api/artifact-types/{id}`)
- [ ] Default types (the 6 seeded ones) show no delete button
- [ ] Editing a type's prompt is possible inline or via edit mode (calls `PATCH /api/artifact-types/{id}`)
- [ ] All changes reflected immediately in the list (optimistic or refetch)

## Tasks
- [ ] Add "Artifacts" nav item to `Sidebar.tsx`
- [ ] Create `frontend/app/projects/[id]/artifacts/page.tsx`
- [ ] Create `frontend/src/components/ArtifactTypeCard.tsx` — expandable card with prompt, edit, delete
- [ ] Create `frontend/src/components/NewArtifactTypeModal.tsx` — name + prompt form
- [ ] Add `artifactTypesAPI` to `frontend/src/api/client.ts` (list, create, patch, delete)
- [ ] Wire delete with confirmation dialog
- [ ] Wire inline prompt editing with save on blur / explicit save button
