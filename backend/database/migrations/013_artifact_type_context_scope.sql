-- Migration 013: add context_scope to artifact_types
-- 'call'    = generate using this call's transcript + topics only
-- 'project' = generate using this call's transcript + topics + accumulated project topics
-- Run in Supabase SQL editor

SET search_path = public;

ALTER TABLE public.artifact_types
  ADD COLUMN IF NOT EXISTS context_scope TEXT NOT NULL DEFAULT 'call'
  CHECK (context_scope IN ('call', 'project'));
