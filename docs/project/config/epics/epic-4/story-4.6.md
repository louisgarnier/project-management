# Story 4.6 — Context File Attachments

**Epic:** EPIC-4 — Transcript Stage
**Status:** `done`
**Depends on:** Story 4.5

---

## Goal
The user can attach supplementary files to a call in the Get Transcript stage. These files provide additional context used later when drafting artifacts. Files are stored in Supabase Storage and remain accessible from all subsequent stages.

## Acceptance Criteria

### Infrastructure
- [x] Supabase Storage bucket `call-files` created (private, authenticated access only)
- [x] ADR written for Supabase Storage adoption (ADR-002)

### Backend
- [x] New `call_files` table:
  - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
  - `call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE`
  - `filename TEXT NOT NULL`
  - `storage_path TEXT NOT NULL`
  - `size_bytes INTEGER`
  - `created_at TIMESTAMPTZ DEFAULT NOW()`
- [x] `POST /api/calls/{call_id}/files` — upload file to Supabase Storage, create DB record
  - Accepted formats: `.txt`, `.pdf`, `.docx`, `.csv`, `.md`
  - Max size: 10MB
  - 404 if call not found
  - 422 if file type not accepted or exceeds size limit
- [x] `GET /api/calls/{call_id}/files` — return list of attached files (id, filename, size_bytes, created_at)
- [x] `DELETE /api/calls/{call_id}/files/{file_id}` — delete from Supabase Storage + DB record
  - 404 if file not found
- [x] `GET /api/calls/{call_id}/files/{file_id}/download` — return signed download URL (60s expiry)
- [x] All endpoints logged and tested (10 tests)

### Frontend — Get Transcript Stage (review screen, after 4.5)
- [x] "Context Files" section shown below transcript textarea
- [x] Upload button: accepts .txt, .pdf, .docx, .csv, .md (max 10MB)
- [x] File list shows: filename, size, upload date, download icon, delete icon
- [x] Delete: confirmation prompt before removing
- [x] Upload error shown inline (wrong type, too large, server error)

### Frontend — All Post-Transcript Stages (Artifacts, Topics, Done)
- [x] Context files panel visible as a section on call detail page
- [x] Download only — no upload or delete from later stages

## Tasks
- [x] Supabase: create `call-files` Storage bucket + RLS policy
- [x] Supabase migration: create `call_files` table
- [x] Backend: `POST /api/calls/{id}/files` (multipart upload → Supabase Storage)
- [x] Backend: `GET /api/calls/{id}/files`
- [x] Backend: `DELETE /api/calls/{id}/files/{file_id}`
- [x] Backend: `GET /api/calls/{id}/files/{file_id}/download` (signed URL)
- [x] Backend tests: upload, list, delete, download, 404s, 422s (10 tests)
- [x] Frontend: `filesAPI` in `client.ts`
- [x] Frontend: `ContextFiles.tsx` component (upload + list + delete)
- [x] Frontend: wire into Get Transcript review screen (Story 4.5)
- [x] Frontend: wire read-only panel into call detail page for post-transcript stages

## Extra features built this story
- Delete project UI (Sidebar.tsx — calls existing `DELETE /api/projects/{id}`)
- Reset transcript: `DELETE /api/calls/{call_id}/transcript` (rolls back artifacts → transcript, clears transcript + transcript_source in DB)
- Transcript review/validate screen before advancing to Artifacts
- Estimated remaining time during transcription (formula: `15 + 8s/MB`)
- Metal shader warm-up at transcription server startup (eliminates first-run latency spike)
