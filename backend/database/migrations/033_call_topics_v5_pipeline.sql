-- Migration 033: EPIC-17 — call_topics v5 pipeline (13-stage architecture)
--
-- 1. New table `topic_registry` — per-project controlled vocabulary of canonical
--    topic names. Mutated only via Stage 11 human approval. Stage 5 (LLM clustering)
--    receives this list in-context as preferred vocabulary.
--
-- 2. New columns on `calls`:
--    - call_topics_v5_state: pipeline state machine (idle → running → awaiting_review → done | failed)
--    - call_topics_v5_payload: JSONB blob with per-stage outputs + review_payload
--      (approvals_needed, confidence_review, warnings)
--
-- The v4 single-shot path remains in place; v5 is gated behind a feature flag
-- (Task 5.10). Soft cutover: existing calls keep extracting via v4 until the
-- flag is flipped.
--
-- ZERO-DOWNTIME: all additions are nullable / defaulted. No data backfill needed.

-- ── 1. topic_registry ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topic_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- which call approved this entry (Stage 11). NULL = manually seeded or imported.
  approved_by_call_id UUID REFERENCES calls(id) ON DELETE SET NULL
);

-- Case-insensitive unique per project (LOWER() index — Postgres-portable)
CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_registry_project_name_lower
  ON topic_registry (project_id, LOWER(name));

CREATE INDEX IF NOT EXISTS idx_topic_registry_project
  ON topic_registry (project_id);

COMMENT ON TABLE topic_registry IS
  'EPIC-17: per-project canonical topic names. Stage 5 reads this as preferred vocabulary. Stage 11 (human approval) is the only insert path.';

-- ── 2. calls.call_topics_v5_state + payload ─────────────────────────────────
ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS call_topics_v5_state TEXT NOT NULL DEFAULT 'idle';

-- CHECK constraint added separately to be idempotent if the column already exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'calls_call_topics_v5_state_check'
  ) THEN
    ALTER TABLE public.calls
      ADD CONSTRAINT calls_call_topics_v5_state_check
      CHECK (call_topics_v5_state IN ('idle', 'running', 'awaiting_review', 'done', 'failed'));
  END IF;
END $$;

ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS call_topics_v5_payload JSONB DEFAULT NULL;

COMMENT ON COLUMN public.calls.call_topics_v5_state IS
  'EPIC-17: v5 pipeline state machine. idle→running→(awaiting_review|done|failed).';
COMMENT ON COLUMN public.calls.call_topics_v5_payload IS
  'EPIC-17: per-stage outputs + review_payload (approvals_needed, confidence_review, warnings). Shape: {stages: {0..12}, review_payload: {...}, started_at, completed_at, model_used, params}.';
