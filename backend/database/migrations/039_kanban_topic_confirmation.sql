-- EPIC-20: add 'topic_confirmation' to the kanban_stage CHECK constraint
-- This was missed in migrations 037/038.

ALTER TABLE public.calls DROP CONSTRAINT IF EXISTS calls_kanban_stage_check;
ALTER TABLE public.calls
  ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN (
    'transcript',
    'call_topics',
    'topic_confirmation',
    'project_matching',
    'project_updates',
    'artifacts',
    'done'
  ));

NOTIFY pgrst, 'reload schema';
