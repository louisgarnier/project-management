-- Migration 006: add deepseek as allowed LLM provider
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_mode_check;

ALTER TABLE artifacts
  ADD CONSTRAINT artifacts_mode_check
  CHECK (mode IN ('groq', 'deepseek', 'claude', 'openai', 'manual'));

-- Verify
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'artifacts'::regclass AND contype = 'c';
