-- 009_call_lock_stale.sql
-- Add lock and stale tracking to calls table.
-- Expand artifact status to include 'stale'.
-- Run once in Supabase SQL editor.

ALTER TABLE calls ADD COLUMN IF NOT EXISTS is_locked boolean NOT NULL DEFAULT false;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS topics_stale boolean NOT NULL DEFAULT false;

-- Expand the artifact status constraint to allow 'stale'
ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_status_check;
ALTER TABLE artifacts ADD CONSTRAINT artifacts_status_check
  CHECK (status IN ('pending', 'generating', 'done', 'error', 'stale'));
