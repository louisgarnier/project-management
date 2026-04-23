-- 020_add_openrouter_mode.sql
-- EPIC-11: add 'openrouter' to artifacts.mode CHECK constraint
-- Run in Supabase Dashboard → SQL Editor → New query

ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_mode_check;

ALTER TABLE artifacts
  ADD CONSTRAINT artifacts_mode_check
  CHECK (mode IN ('groq', 'deepseek', 'claude', 'openai', 'openrouter', 'manual'));

-- Verify
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'artifacts'::regclass AND contype = 'c';
