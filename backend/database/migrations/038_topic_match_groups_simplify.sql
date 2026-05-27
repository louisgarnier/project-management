-- EPIC-20 Stage 2: one topic per group; explicit group_kind enum
-- Replaces EPIC-19's multi-topic primary-target hack.
--
-- New code paths use finalized_topic_id + group_kind.
-- Old columns (project_topic_ids, target_topic_name, project_task_refs multi-topic
-- semantics, kind 'binding'/'topic_merge') remain on the table for rollback safety
-- and are populated/read by the backfill script during transition.

ALTER TABLE topic_match_groups
    ADD COLUMN IF NOT EXISTS finalized_topic_id UUID REFERENCES call_finalized_topics(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS group_kind TEXT CHECK (group_kind IN ('new_only', 'old_only', 'mixed'));

CREATE INDEX IF NOT EXISTS idx_tmg_finalized_topic ON topic_match_groups(finalized_topic_id);

COMMENT ON COLUMN topic_match_groups.finalized_topic_id IS
'EPIC-20: the single finalized topic this group targets (one group → one topic by construction)';

COMMENT ON COLUMN topic_match_groups.group_kind IS
'EPIC-20: ''new_only'' (Pass 1), ''old_only'' (Pass 2), ''mixed'' (Pass 3). Computed from refs; persisted for routing.';

NOTIFY pgrst, 'reload schema';
