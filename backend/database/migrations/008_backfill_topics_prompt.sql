-- 008_backfill_topics_prompt.sql
-- Insert topics extraction prompt for projects created before migration 007.
-- Run once in Supabase SQL editor after deploying 007_artifact_type_category.sql.

INSERT INTO artifact_types (project_id, name, prompt, is_default, category)
SELECT
  p.id,
  'Topics Extraction',
  E'You are an expert at extracting business topics from client call transcripts.\n\nExtract all key business topics discussed. For each topic return a JSON object matching:\n{"name":"string","summary":"string","follow_up_items":["string"],"decisions":["string"],"status":"open|in_progress|resolved","owner":"Us|Client|Both","sentiment":"positive|neutral|concern"}\n\nFocus on: decisions made, open questions, action items, relationship dynamics, technical blockers.\nBe specific — "Pricing" not "Discussion", "API Integration Timeline" not "Technical".',
  true,
  'topics'
FROM projects p
WHERE NOT EXISTS (
  SELECT 1 FROM artifact_types a
  WHERE a.project_id = p.id AND a.category = 'topics'
);
