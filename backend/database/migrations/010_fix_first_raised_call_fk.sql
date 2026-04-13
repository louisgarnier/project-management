-- 010_fix_first_raised_call_fk.sql
-- Run in Supabase Dashboard → SQL Editor → New query
--
-- Problem: topics.first_raised_call_id references calls(id) with no ON DELETE clause,
-- which defaults to RESTRICT. Deleting a call that first raised any topic fails with
-- a FK constraint violation (HTTP 500).
--
-- Fix: change to ON DELETE SET NULL — the topic is preserved, the pointer is cleared.

ALTER TABLE topics
  DROP CONSTRAINT IF EXISTS topics_first_raised_call_id_fkey;

ALTER TABLE topics
  ADD CONSTRAINT topics_first_raised_call_id_fkey
  FOREIGN KEY (first_raised_call_id)
  REFERENCES calls(id)
  ON DELETE SET NULL;
