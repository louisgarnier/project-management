-- Migration 016: Add merge_cache and merge_status to calls table
-- Mirrors the extraction_cache / extraction_status pattern for background merge previews.

ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS merge_cache  JSONB,
  ADD COLUMN IF NOT EXISTS merge_status TEXT NOT NULL DEFAULT 'idle'
    CHECK (merge_status IN ('idle', 'processing', 'done', 'failed'));
