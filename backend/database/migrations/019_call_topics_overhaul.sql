-- 019_call_topics_overhaul.sql
-- EPIC-11: Call Topics Extraction Overhaul — schema additions
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. topic_updates: four new columns for the richer schema
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS is_parked BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS importance TEXT NOT NULL DEFAULT 'medium',
  ADD COLUMN IF NOT EXISTS rationale TEXT NOT NULL DEFAULT '';

-- 2. artifact_types: model column for OpenRouter slugs
ALTER TABLE public.artifact_types
  ADD COLUMN IF NOT EXISTS model TEXT DEFAULT NULL;

-- 3. projects: default_model column for project-level OpenRouter default
ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS default_model TEXT DEFAULT NULL;
