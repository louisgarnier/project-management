-- EPIC-18: unified read model for project topic state
-- Consumed by v5 Stage 1 (clustering context) and Pass 1 (verify_new)
-- Joins topics + latest topic_updates per topic, project-scoped.

CREATE OR REPLACE VIEW project_topic_state AS
SELECT
    t.id AS topic_id,
    t.project_id,
    t.name,
    t.calls_open,
    t.first_raised_call_id,
    t.archived,
    COALESCE(latest.summary, '')          AS summary,
    COALESCE(latest.status, 'open')        AS status,
    COALESCE(latest.sentiment, 'neutral')  AS sentiment,
    COALESCE(latest.importance, 'medium')  AS importance,
    COALESCE(latest.evidence, '[]'::jsonb) AS evidence,
    COALESCE(latest.key_terms, '[]'::jsonb) AS key_terms,
    COALESCE(latest.tasks, '[]'::jsonb)    AS tasks,
    COALESCE(latest.open_questions, '[]'::jsonb) AS open_questions,
    COALESCE(latest.decisions, '[]'::jsonb) AS decisions,
    latest.chronology_narrative,
    latest.rag_verification_note,
    latest.created_at AS latest_update_at
FROM topics t
LEFT JOIN LATERAL (
    SELECT *
    FROM topic_updates u
    WHERE u.topic_id = t.id
    ORDER BY u.created_at DESC
    LIMIT 1
) latest ON true
WHERE t.archived = false;

COMMENT ON VIEW project_topic_state IS
'EPIC-18 unified read model. Use this view (not raw topic_registry / topic_updates queries) when loading project state for v5 clustering or Pass 1 verification.';
