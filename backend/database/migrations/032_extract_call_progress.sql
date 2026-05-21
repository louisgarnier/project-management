-- Migration 032: EPIC-16 — call_topics extraction progress log.
--
-- Adds a JSONB column on `calls` to stream per-step progress entries from the
-- background extraction task to the frontend. Mirrors the verify_*_cache /
-- extract_updates_cache pattern used by Pass ①/②/③.
--
-- Shape: { "__progress__": [{"ts": "<iso>", "msg": "..."}, ...] }
-- Cleared (set NULL) when a new extraction starts; flushed continuously
-- during the run; remains visible after completion as an audit trail.
--
-- ZERO-DOWNTIME: column is nullable, no default rewrite needed.

ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS extract_call_progress JSONB DEFAULT NULL;

COMMENT ON COLUMN public.calls.extract_call_progress IS
  'EPIC-16: progress log for background call_topics extraction. Shape: {__progress__: [{ts, msg}]}';
