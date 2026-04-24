-- 023_library_category.sql
-- EPIC-12 follow-up: artifact_library gains a category column so Tier-1 workflow
-- prompts (call_topics, project_topics, merge_verification, not_discussed_check)
-- can live alongside Tier-2 artifact prompts in the shared library.
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

ALTER TABLE public.artifact_library
  ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'artifacts';

ALTER TABLE public.artifact_library
  DROP CONSTRAINT IF EXISTS artifact_library_category_check;
ALTER TABLE public.artifact_library
  ADD CONSTRAINT artifact_library_category_check
  CHECK (category IN ('artifacts', 'call_topics', 'project_topics', 'merge_verification', 'not_discussed_check'));

-- Verify
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'artifact_library' AND column_name = 'category';
