-- 030_epic16_rag_passes.sql
-- EPIC-16: Project Updates RAG rework
-- Manual application required via Supabase dashboard before backend restart.

-- 1. New status/cache columns on calls (6 total)
ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS verify_new_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS verify_new_cache JSONB,
  ADD COLUMN IF NOT EXISTS verify_not_discussed_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS verify_not_discussed_cache JSONB,
  ADD COLUMN IF NOT EXISTS extract_updates_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS extract_updates_cache JSONB;

-- 2. Citation + evidence_trail + needs_manual_review on topic_updates
ALTER TABLE topic_updates
  ADD COLUMN IF NOT EXISTS citations JSONB,
  ADD COLUMN IF NOT EXISTS evidence_trail JSONB,
  ADD COLUMN IF NOT EXISTS needs_manual_review BOOLEAN NOT NULL DEFAULT false;

-- 3. Soft-deprecate the 3 old workflow prompt library entries
UPDATE artifact_library
SET seeded_by_default = false, is_system = false
WHERE category IN ('project_topics', 'merge_verification', 'not_discussed_check')
  AND is_system = true;
