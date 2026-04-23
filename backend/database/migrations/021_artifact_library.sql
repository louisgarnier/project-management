-- 021_artifact_library.sql
-- EPIC-12: Artifacts Overhaul — kind/template_id/library_ref_id columns + artifact_library table
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. Extend artifact_types with new columns
ALTER TABLE public.artifact_types
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'llm',
  ADD COLUMN IF NOT EXISTS template_id TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS library_ref_id UUID DEFAULT NULL;

ALTER TABLE public.artifact_types
  DROP CONSTRAINT IF EXISTS artifact_types_kind_check;
ALTER TABLE public.artifact_types
  ADD CONSTRAINT artifact_types_kind_check
  CHECK (kind IN ('llm', 'template', 'hybrid'));

-- 2. Create artifact_library table
CREATE TABLE IF NOT EXISTS public.artifact_library (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'llm' CHECK (kind IN ('llm', 'template', 'hybrid')),
  prompt TEXT DEFAULT NULL,
  template_id TEXT DEFAULT NULL,
  llm TEXT DEFAULT NULL,
  model TEXT DEFAULT NULL,
  context_scope TEXT NOT NULL DEFAULT 'call' CHECK (context_scope IN ('call', 'project')),
  is_system BOOLEAN NOT NULL DEFAULT FALSE,
  seeded_by_default BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. FK from artifact_types.library_ref_id → artifact_library.id
ALTER TABLE public.artifact_types
  DROP CONSTRAINT IF EXISTS artifact_types_library_ref_fkey;
ALTER TABLE public.artifact_types
  ADD CONSTRAINT artifact_types_library_ref_fkey
  FOREIGN KEY (library_ref_id) REFERENCES public.artifact_library(id) ON DELETE SET NULL;

-- Verify
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'artifact_types' AND column_name IN ('kind', 'template_id', 'library_ref_id');

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'artifact_library';
