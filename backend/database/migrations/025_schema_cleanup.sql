-- Migration 025 — schema cleanup
--
-- Drops unused tables, columns, and CHECK constraint extensions that were
-- applied to Supabase by abandoned work. Restores the schema to the state
-- it had after migration 024.
--
-- Pre-conditions (already done by the cleanup script):
--   • Stale artifact_library rows (categories match_to_priors / verify_match /
--     topic_update_check / extract_atomic) deleted.
--   • Test projects deleted, cascade-clearing their downstream rows.
--
-- Run manually in Supabase Dashboard → SQL Editor.

SET search_path = public;

-- ── Drop unused tables ──
DROP TABLE IF EXISTS public.tracker_snapshots;
DROP TABLE IF EXISTS public.atomic_action_items;
DROP TABLE IF EXISTS public.commit_log;
DROP TABLE IF EXISTS public.call_prompt_snapshots;

-- ── Drop unused columns on projects ──
ALTER TABLE public.projects
  DROP CONSTRAINT IF EXISTS projects_pipeline_mode_check,
  DROP COLUMN IF EXISTS pipeline_mode;

-- ── Drop unused columns on calls ──
ALTER TABLE public.calls
  DROP COLUMN IF EXISTS pending_carryover,
  DROP COLUMN IF EXISTS pending_carryover_at;

-- ── Drop unused columns on topics ──
ALTER TABLE public.topics
  DROP COLUMN IF EXISTS is_archived;

-- ── Drop unused columns on topic_updates ──
DROP INDEX IF EXISTS idx_topic_updates_commit_state;
ALTER TABLE public.topic_updates
  DROP CONSTRAINT IF EXISTS topic_updates_commit_state_check,
  DROP COLUMN IF EXISTS confidence_total,
  DROP COLUMN IF EXISTS confidence_signals,
  DROP COLUMN IF EXISTS evidence_excerpt,
  DROP COLUMN IF EXISTS commit_state;

-- ── Restore artifact_library.category CHECK to the 5-category baseline ──
ALTER TABLE public.artifact_library
  DROP CONSTRAINT IF EXISTS artifact_library_category_check;
ALTER TABLE public.artifact_library
  ADD CONSTRAINT artifact_library_category_check
  CHECK (category IN (
    'artifacts',
    'call_topics',
    'project_topics',
    'merge_verification',
    'not_discussed_check'
  ));

-- ── Restore artifact_types.category CHECK (if the column exists) ──
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'artifact_types' AND column_name = 'category'
  ) THEN
    ALTER TABLE public.artifact_types
      DROP CONSTRAINT IF EXISTS artifact_types_category_check;
    ALTER TABLE public.artifact_types
      ADD CONSTRAINT artifact_types_category_check
      CHECK (category IN (
        'artifacts',
        'call_topics',
        'project_topics',
        'merge_verification',
        'not_discussed_check'
      ));
  END IF;
END $$;

-- ── Restore calls.kanban_stage CHECK to the 6-stage baseline ──
ALTER TABLE public.calls DROP CONSTRAINT IF EXISTS calls_kanban_stage_check;
ALTER TABLE public.calls ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN (
    'transcript',
    'call_topics',
    'project_matching',
    'project_updates',
    'artifacts',
    'done'
  ));

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';
