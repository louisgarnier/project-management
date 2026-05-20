-- 031_epic16_category_whitelist.sql
-- EPIC-16 follow-up to migration 030.
-- The CHECK constraints on artifact_library.category and artifact_types.category
-- (set by migration 025) restrict to 5 legacy categories. EPIC-16 introduces 3
-- new workflow categories — extend both constraints to allow them.
-- Manual application required via Supabase dashboard.

-- ── artifact_library.category ──
ALTER TABLE public.artifact_library
  DROP CONSTRAINT IF EXISTS artifact_library_category_check;

ALTER TABLE public.artifact_library
  ADD CONSTRAINT artifact_library_category_check
  CHECK (category IN (
    'artifacts',
    'call_topics',
    'project_topics',
    'merge_verification',
    'not_discussed_check',
    'verify_new_topic',
    'verify_not_discussed',
    'extract_topic_updates'
  ));

-- ── artifact_types.category (only if column exists) ──
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'artifact_types'
      AND column_name = 'category'
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
        'not_discussed_check',
        'verify_new_topic',
        'verify_not_discussed',
        'extract_topic_updates'
      ));
  END IF;
END $$;
