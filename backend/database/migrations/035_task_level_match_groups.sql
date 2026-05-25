-- EPIC-19: task-level match groups
-- Extends topic_match_groups with task-level references.
-- Old call_topic_names + project_topic_ids retained for back-compat reads;
-- new task-level work uses call_task_refs + project_task_refs.

ALTER TABLE topic_match_groups
  ADD COLUMN IF NOT EXISTS call_task_refs JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS project_task_refs JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS kind TEXT DEFAULT 'binding'
    CHECK (kind IN ('binding', 'topic_merge'));

COMMENT ON COLUMN topic_match_groups.call_task_refs IS
'EPIC-19: list of {call_topic_name, task_id} referencing pending tasks from v5 output of this call';

COMMENT ON COLUMN topic_match_groups.project_task_refs IS
'EPIC-19: list of {project_topic_id, task_id} referencing existing tasks in project_topic_state';

COMMENT ON COLUMN topic_match_groups.kind IS
'EPIC-19: ''binding'' = task-to-task N:M match; ''topic_merge'' = explicit cross-topic merge decision';

-- Index for the common "fetch all groups for a call" query
CREATE INDEX IF NOT EXISTS idx_topic_match_groups_call_kind
  ON topic_match_groups(call_id, kind);
