-- 024_system_settings.sql
-- EPIC-12 follow-up: singleton system_settings table for the root of the LLM/model cascade.
-- Also makes projects.default_llm nullable so 'inherit system' becomes a first-class state.
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. system_settings singleton
CREATE TABLE IF NOT EXISTS public.system_settings (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  default_llm TEXT NOT NULL DEFAULT 'openrouter',
  default_model TEXT DEFAULT 'deepseek/deepseek-v3.2',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO public.system_settings (id, default_llm, default_model)
VALUES (1, 'openrouter', 'deepseek/deepseek-v3.2')
ON CONFLICT (id) DO NOTHING;

-- 2. Make projects.default_llm nullable (inherit when null)
ALTER TABLE public.projects
  ALTER COLUMN default_llm DROP NOT NULL;
-- Keep existing non-null values intact; new projects can now insert NULL to mean "inherit".

-- Verify
SELECT * FROM system_settings;
SELECT column_name, is_nullable FROM information_schema.columns
WHERE table_name = 'projects' AND column_name = 'default_llm';
