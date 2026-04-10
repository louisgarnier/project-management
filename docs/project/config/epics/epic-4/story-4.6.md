# Story 4.6 — Context File Attachments

**Epic:** EPIC-4 — Transcript Stage
**Status:** `pending`
**Depends on:** Story 4.5

---

## Goal
The user can attach supplementary files to a call in the Get Transcript stage. These files provide additional context used later when drafting artifacts. Files are stored in Supabase Storage and remain accessible from all subsequent stages.

## Acceptance Criteria

### Infrastructure
- [ ] Supabase Storage bucket `call-files` created (private, authenticated access only)
- [ ] ADR written for Supabase Storage adoption

### Backend
- [ ] New `call_files` table:
  - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  - `call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE`
  - `filename TEXT NOT NULL`
  - `storage_path TEXT NOT NULL`
  - `size_bytes INTEGER`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`
- [ ] `POST /api/calls/{call_id}/files` — upload file to Supabase Storage, create DB record
  - Accepted formats: `.txt`, `.pdf`, `.docx`, `.csv`, `.md`
  - Max size: 10MB
  - 404 if call not found
  - 422 if file type not accepted or exceeds size limit
- [ ] `GET /api/calls/{call_id}/files` — return list of attached files (id, filename, size_bytes, created_at)
- [ ] `DELETE /api/calls/{call_id}/files/{file_id}` — delete from Supabase Storage + DB record
  - 404 if file not found
- [ ] `GET /api/calls/{call_id}/files/{file_id}/download` — return signed download URL (60s expiry)
- [ ] All endpoints logged and tested

### Frontend — Get Transcript Stage (review screen, after 4.5)
- [ ] "Context Files" section shown below transcript textarea
- [ ] Upload button: accepts .txt, .pdf, .docx, .csv, .md (max 10MB)
- [ ] File list shows: filename, size, upload date, download icon, delete icon
- [ ] Delete: confirmation prompt before removing
- [ ] Upload error shown inline (wrong type, too large, server error)

### Frontend — All Post-Transcript Stages (Artifacts, Topics, Done)
- [ ] Context files panel visible as a collapsible sidebar or section
- [ ] Download only — no upload or delete from later stages

## Tasks
- [ ] Supabase: create `call-files` Storage bucket + RLS policy
- [ ] Supabase migration: create `call_files` table
- [ ] Backend: `POST /api/calls/{id}/files` (multipart upload → Supabase Storage)
- [ ] Backend: `GET /api/calls/{id}/files`
- [ ] Backend: `DELETE /api/calls/{id}/files/{file_id}`
- [ ] Backend: `GET /api/calls/{id}/files/{file_id}/download` (signed URL)
- [ ] Backend tests: upload, list, delete, download, 404s, 422s
- [ ] Frontend: `filesAPI` in `client.ts`
- [ ] Frontend: `ContextFiles.tsx` component (upload + list + delete)
- [ ] Frontend: wire into Get Transcript review screen (Story 4.5)
- [ ] Frontend: wire read-only panel into call detail page for post-transcript stages
