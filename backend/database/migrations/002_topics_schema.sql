-- 002_topics_schema.sql
-- Run in Supabase Dashboard → SQL Editor → New query

-- Drop old status constraint on topics (status is now tracked per-call in topic_updates)
ALTER TABLE topics DROP CONSTRAINT IF EXISTS topics_status_check;
ALTER TABLE topics DROP COLUMN IF EXISTS status;

-- Add new columns to topics
ALTER TABLE topics
  ADD COLUMN IF NOT EXISTS calls_open  INT  NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS archived    BOOL NOT NULL DEFAULT FALSE;

-- Add new columns to topic_updates
ALTER TABLE topic_updates
  ADD COLUMN IF NOT EXISTS decisions   JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS status      TEXT  NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'in_progress', 'resolved')),
  ADD COLUMN IF NOT EXISTS owner       TEXT  NOT NULL DEFAULT 'Us'
    CHECK (owner IN ('Us', 'Client', 'Both')),
  ADD COLUMN IF NOT EXISTS sentiment   TEXT  NOT NULL DEFAULT 'neutral'
    CHECK (sentiment IN ('positive', 'neutral', 'concern'));
