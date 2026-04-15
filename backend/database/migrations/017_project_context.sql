-- Migration 017: add context field to projects
-- Stores free-text project context injected into all LLM prompts

ALTER TABLE projects ADD COLUMN IF NOT EXISTS context TEXT;
