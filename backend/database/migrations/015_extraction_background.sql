-- 015_extraction_background.sql
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- Add background extraction tracking columns to calls
ALTER TABLE public.calls
  ADD COLUMN IF NOT EXISTS extraction_cache JSONB NULL,
  ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'idle';

-- Add check constraint for extraction_status
DO $$
DECLARE
  cname TEXT;
BEGIN
  SELECT conname INTO cname
  FROM pg_constraint
  WHERE conrelid = 'public.calls'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) LIKE '%extraction_status%';
  IF cname IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.calls DROP CONSTRAINT ' || quote_ident(cname);
  END IF;
END $$;

ALTER TABLE public.calls ADD CONSTRAINT calls_extraction_status_check
  CHECK (extraction_status IN ('idle', 'processing', 'done', 'failed'));
