-- EPIC-20 Stage 1: per-call finalized topic list
-- The user's topic-lifecycle decisions for each call.
-- - 'existing' rows reference topic_registry.id (carried-forward topic, possibly renamed)
-- - 'new' rows have topic_id = NULL until materialised in topic_registry

CREATE TABLE IF NOT EXISTS call_finalized_topics (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id       UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    topic_id      UUID REFERENCES topic_registry(id) ON DELETE SET NULL,
    name          TEXT NOT NULL,
    source        TEXT NOT NULL CHECK (source IN ('existing', 'new')),
    v5_cluster_id TEXT,
    position      INT  NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cft_call_id ON call_finalized_topics(call_id);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_cft_call_name ON call_finalized_topics(call_id, name);

COMMENT ON TABLE call_finalized_topics IS
'EPIC-20 Stage 1: finalized topic list per call. Output of the topic_confirmation kanban stage.';

NOTIFY pgrst, 'reload schema';
