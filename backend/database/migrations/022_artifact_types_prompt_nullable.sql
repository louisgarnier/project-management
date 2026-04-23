-- 022_artifact_types_prompt_nullable.sql
-- EPIC-12: template-kind artifact types legitimately have no prompt (logic lives in Python).
-- Hybrid-kind artifact types store JSON {intro, closing} so they do have a prompt.
-- LLM-kind still has a prompt. Nullable is the right semantic now that kind varies.
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

ALTER TABLE public.artifact_types
  ALTER COLUMN prompt DROP NOT NULL;

-- Verify
SELECT column_name, is_nullable
FROM information_schema.columns
WHERE table_name = 'artifact_types' AND column_name = 'prompt';
-- Expected: is_nullable = YES
