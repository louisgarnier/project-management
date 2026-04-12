-- 003_artifact_types_project_scoped.sql
-- Scopes artifact_types to a project. Removes the global seed — defaults are
-- now seeded per-project at creation time via the API.
-- Run in Supabase Dashboard → SQL Editor → New query.

ALTER TABLE artifact_types
  ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE CASCADE;

-- Remove existing global seed rows (they have no project_id and are invalid)
DELETE FROM artifact_types;

ALTER TABLE artifact_types
  ALTER COLUMN project_id SET NOT NULL;
