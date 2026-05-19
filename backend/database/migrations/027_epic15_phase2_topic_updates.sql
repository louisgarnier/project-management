-- Migration 027 — EPIC-15 Phase 2 / Story 15.5:
-- Add open_questions + decisions JSONB cols on topic_updates.
-- Pre-install chronology_narrative + rag_verification_note TEXT cols
-- (Story 15.7 populates them — added here to keep migration count low).
-- Demote v2 call_topics library entry so v3 becomes the seeded default.
--
-- Run manually in Supabase Dashboard → SQL Editor.
-- (context_scope CHECK enum update ships separately in migration 028
--  with Story 15.6, since 15.5 and 15.6 are parallel-safe.)

SET search_path = public;

-- ── 1. topic_updates: new columns ──
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS open_questions        JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS decisions             JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS chronology_narrative  TEXT,
  ADD COLUMN IF NOT EXISTS rag_verification_note TEXT;

-- ── 2. Demote v2 library entry so the new v3 entry becomes the default ──
-- Targets the system row only; per-project user copies (stored elsewhere) are unaffected.
-- is_system guard prevents demoting a user row that happens to share the same name.
UPDATE public.artifact_library
   SET seeded_by_default = false
 WHERE name = 'Call Topics — v2 (synthetic, evidence-anchored)'
   AND is_system = true;

-- Reload PostgREST schema cache so the new columns are queryable immediately.
NOTIFY pgrst, 'reload schema';
