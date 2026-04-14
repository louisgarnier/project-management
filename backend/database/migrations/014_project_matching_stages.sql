-- 014_project_matching_stages.sql
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. Drop whatever check constraint exists on kanban_stage (find actual name)
DO $$
DECLARE
  cname TEXT;
BEGIN
  SELECT conname INTO cname
  FROM pg_constraint
  WHERE conrelid = 'public.calls'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%kanban_stage%';
  IF cname IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.calls DROP CONSTRAINT ' || quote_ident(cname);
  END IF;
END $$;

-- 2. Migrate existing project_topics rows → project_matching
--    (they haven't been matched yet so they belong at the matching step)
UPDATE public.calls SET kanban_stage = 'project_matching'
  WHERE kanban_stage = 'project_topics';

-- 3. Add new constraint with all valid values
ALTER TABLE public.calls ADD CONSTRAINT calls_kanban_stage_check
  CHECK (kanban_stage IN ('transcript','call_topics','project_matching','project_updates','artifacts','done'));

-- 4. Add pending_topics column (stores validated call topics between stages)
ALTER TABLE public.calls ADD COLUMN IF NOT EXISTS pending_topics JSONB;

-- 5. Create topic_match_groups table
CREATE TABLE IF NOT EXISTS public.topic_match_groups (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id          UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
  project_topic_id UUID REFERENCES public.topics(id) ON DELETE SET NULL,
  call_topic_names TEXT[] NOT NULL DEFAULT '{}',
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_match_groups_call_id
  ON public.topic_match_groups(call_id);
