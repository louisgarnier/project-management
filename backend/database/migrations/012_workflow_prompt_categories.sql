-- Migration 012: rename topics prompt → call_topics, add project_topics prompt
-- Run in Supabase SQL editor

SET search_path = public;

-- 0. Expand the category check constraint to allow new workflow categories
ALTER TABLE public.artifact_types
  DROP CONSTRAINT IF EXISTS artifact_types_category_check;

ALTER TABLE public.artifact_types
  ADD CONSTRAINT artifact_types_category_check
  CHECK (category IN ('artifacts', 'topics', 'call_topics', 'project_topics'));

-- 1. Rename existing "Topics Extraction" prompt to "Call Topics Extraction" with call_topics category
UPDATE public.artifact_types
SET category = 'call_topics',
    name = 'Call Topics Extraction'
WHERE category = 'topics';

-- 2. Insert "Project Topics Merge" for every project that now has a call_topics prompt
INSERT INTO public.artifact_types (project_id, name, prompt, is_default, category, llm)
SELECT
  project_id,
  'Project Topics Merge',
  'You are an expert at matching client call topics to an existing project topic backlog.

Given topics extracted from the current call and the existing project topic list, classify each topic:
- "followed_up": call topics that match an existing project topic (same business subject, possibly different wording). Use the existing topic name exactly. Update summary, status, follow_up_items, and decisions with new information from this call.
- "not_discussed": existing project topics not covered by any call topic.
- "new_topics": call topics with no match in the existing project list.

Be generous with matching — slightly different wording for the same business subject counts as a match.',
  TRUE,
  'project_topics',
  NULL
FROM public.artifact_types
WHERE category = 'call_topics';
