-- Migration 002: add transcript_source to calls
-- Run in Supabase Dashboard → SQL Editor → New query

ALTER TABLE calls ADD COLUMN IF NOT EXISTS transcript_source TEXT;
