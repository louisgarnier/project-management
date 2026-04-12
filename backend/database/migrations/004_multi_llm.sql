-- Migration 004: multi-LLM support
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS default_llm TEXT NOT NULL DEFAULT 'groq';

ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS llm TEXT;

-- Verify
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name IN ('projects', 'artifact_types')
  AND column_name IN ('default_llm', 'llm')
ORDER BY table_name, column_name;
