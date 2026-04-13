-- Migration 005: expand artifacts.mode check constraint to include all LLM providers
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_mode_check;

ALTER TABLE artifacts
  ADD CONSTRAINT artifacts_mode_check
  CHECK (mode IN ('groq', 'claude', 'openai', 'manual'));

-- Verify
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'artifacts'::regclass AND contype = 'c';
