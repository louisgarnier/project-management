-- 005_artifact_type_category.sql
-- Add category to artifact_types: 'artifacts' (default) or 'topics'

ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'artifacts'
  CHECK (category IN ('artifacts', 'topics'));
