-- 011_two_step_topics_stages.sql
-- Run in Supabase Dashboard → SQL Editor → New query
--
-- Replaces the single 'topics' kanban stage with two stages:
--   call_topics     — Step 1: extract topics from this call only (unbiased)
--   project_topics  — Step 2: match against accumulated project topics (3-bucket review)

-- 1. Drop old constraint
ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_kanban_stage_check;

-- 2. Add new constraint with both new stage values
ALTER TABLE calls
  ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN ('transcript','call_topics','project_topics','artifacts','done'));

-- 3. Migrate existing rows at 'topics' → 'call_topics'
--    (they haven't completed topics review yet, so they restart at Step 1)
UPDATE calls SET kanban_stage = 'call_topics' WHERE kanban_stage = 'topics';
