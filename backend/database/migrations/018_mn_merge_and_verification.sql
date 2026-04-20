-- 018_mn_merge_and_verification.sql
-- EPIC-9: M:N Topic Merge + Not-Discussed Verification
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. topic_updates: add transcript_excerpt column
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS transcript_excerpt TEXT DEFAULT NULL;

-- 2. topics: add merged_into_topic_id column
ALTER TABLE public.topics
  ADD COLUMN IF NOT EXISTS merged_into_topic_id UUID REFERENCES public.topics(id) ON DELETE SET NULL DEFAULT NULL;

-- 3. topic_match_groups: replace project_topic_id (single UUID) with project_topic_ids (UUID array)
ALTER TABLE public.topic_match_groups
  ADD COLUMN IF NOT EXISTS project_topic_ids UUID[] NOT NULL DEFAULT '{}';

-- Migrate existing data: single UUID → array
UPDATE public.topic_match_groups
  SET project_topic_ids = ARRAY[project_topic_id]
  WHERE project_topic_id IS NOT NULL AND project_topic_ids = '{}';

-- Drop old column and its FK constraint
ALTER TABLE public.topic_match_groups
  DROP COLUMN IF EXISTS project_topic_id;

-- 4. calls: add verification fields
ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS verification_cache JSONB DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'idle';

-- Add check constraint for verification_status
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.calls'::regclass
      AND conname = 'calls_verification_status_check'
  ) THEN
    ALTER TABLE public.calls ADD CONSTRAINT calls_verification_status_check
      CHECK (verification_status IN ('idle', 'processing', 'done', 'failed'));
  END IF;
END $$;

-- 5. artifact_types: update category constraint to include 'not_discussed_check'
DO $$
DECLARE
  cname TEXT;
BEGIN
  SELECT conname INTO cname
  FROM pg_constraint
  WHERE conrelid = 'public.artifact_types'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%category%';
  IF cname IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.artifact_types DROP CONSTRAINT ' || quote_ident(cname);
  END IF;
END $$;

ALTER TABLE public.artifact_types ADD CONSTRAINT artifact_types_category_check
  CHECK (category IN ('artifacts', 'topics', 'call_topics', 'project_topics', 'not_discussed_check'));
