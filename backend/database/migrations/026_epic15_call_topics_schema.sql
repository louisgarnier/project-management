-- Migration 026 — EPIC-15: Call Topics Rebuild
--
-- Reshape topic_updates: drop the EPIC-11 5-field anchor structure;
-- replace with 3 JSONB columns (evidence / key_terms / tasks).
-- Add calls.call_topics_prompt_id FK for per-call prompt selection.
--
-- Run manually in Supabase Dashboard → SQL Editor.

SET search_path = public;

-- ── 1. topic_updates: add new columns ──
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS evidence  JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS key_terms JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS tasks     JSONB NOT NULL DEFAULT '[]'::jsonb;

-- ── 2. topic_updates: drop legacy columns ──
ALTER TABLE public.topic_updates
  DROP COLUMN IF EXISTS decisions,
  DROP COLUMN IF EXISTS follow_up_items,
  DROP COLUMN IF EXISTS open_questions,
  DROP COLUMN IF EXISTS rationale,
  DROP COLUMN IF EXISTS is_parked,
  DROP COLUMN IF EXISTS owner;

-- ── 3. calls: per-call prompt selection ──
ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS call_topics_prompt_id UUID NULL
    REFERENCES public.artifact_library(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_calls_prompt_id
  ON public.calls(call_topics_prompt_id);

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';
