-- EPIC-19: optional target topic name for match groups
-- When user explicitly creates a new topic for a binding (via the cross-topic modal),
-- this field carries the name; Pass 3 synthesis uses it as the merged topic's name.
-- Nullable: empty means "use the project_topic's existing name" (default behavior).

ALTER TABLE topic_match_groups
  ADD COLUMN IF NOT EXISTS target_topic_name TEXT;

COMMENT ON COLUMN topic_match_groups.target_topic_name IS
'EPIC-19: optional new topic name chosen by user during cross-topic binding; null means use the existing project topic name';
