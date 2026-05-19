-- Migration 028 — EPIC-15 Phase 2 / Story 15.6: context_scope 4-value enum.
-- Run manually in Supabase Dashboard → SQL Editor.

SET search_path = public;

-- ── 1. Drop old CHECK so we can bulk-update without violations ──
ALTER TABLE public.artifact_library
  DROP CONSTRAINT IF EXISTS artifact_library_context_scope_check;

-- ── 2. Bulk migrate old enum values ──
UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE context_scope = 'call';

UPDATE public.artifact_library
   SET context_scope = 'all_project_topics'
 WHERE context_scope = 'project';

-- ── 3. Explicit per-name overrides (per PRD Q4 mappings) ──
UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE name IN (
   'Executive Summary',
   'Email Summary (1-pager)',
   'Email Follow-up (pre-next-call)',
   'Next Steps & Action Items',
   'Questions for Stakeholders',
   'Decisions Digest'
 );

UPDATE public.artifact_library
   SET context_scope = 'all_project_topics'
 WHERE name IN (
   'Risk Register',
   'Next Call Agenda'
 );

-- Tier-1 workflow prompts: context_scope is pipeline-internal (unused at runtime).
-- Set to 'this_call_topics' to satisfy the new CHECK.
UPDATE public.artifact_library
   SET context_scope = 'this_call_topics'
 WHERE category IN ('call_topics', 'project_topics', 'merge_verification', 'not_discussed_check');

-- ── 4. Same migration on the per-project artifact_types table ──
UPDATE public.artifact_types
   SET context_scope = 'this_call_topics'
 WHERE context_scope = 'call';

UPDATE public.artifact_types
   SET context_scope = 'all_project_topics'
 WHERE context_scope = 'project';

-- ── 5. Re-add CHECK with 4 new values ──
ALTER TABLE public.artifact_library
  ADD CONSTRAINT artifact_library_context_scope_check
  CHECK (context_scope IN (
    'this_call_transcript',
    'all_call_transcripts',
    'this_call_topics',
    'all_project_topics'
  ));

ALTER TABLE public.artifact_types
  DROP CONSTRAINT IF EXISTS artifact_types_context_scope_check;
ALTER TABLE public.artifact_types
  ADD CONSTRAINT artifact_types_context_scope_check
  CHECK (context_scope IN (
    'this_call_transcript',
    'all_call_transcripts',
    'this_call_topics',
    'all_project_topics'
  ));

NOTIFY pgrst, 'reload schema';
