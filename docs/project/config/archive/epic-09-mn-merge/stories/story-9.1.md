# Story 9.1 — DB Migration: M:N Merge + Verification Schema

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §1

---

## Goal
Add all new DB columns and constraints needed for M:N matching, transcript excerpt storage, topic merge tracking, and not-discussed verification.

## Acceptance Criteria
- [ ] `topic_updates.transcript_excerpt TEXT` column exists
- [ ] `topics.merged_into_topic_id UUID REFERENCES topics(id)` column exists
- [ ] `topic_match_groups.project_topic_ids UUID[]` column exists, populated from old `project_topic_id`
- [ ] `topic_match_groups.project_topic_id` column dropped
- [ ] `calls.verification_cache JSONB` column exists
- [ ] `calls.verification_status TEXT` column exists with check constraint
- [ ] `artifact_types` category constraint updated to include `'not_discussed_check'`
- [ ] Migration is idempotent (safe to re-run)

## Tasks
- [ ] Write `backend/database/migrations/018_mn_merge_and_verification.sql`
- [ ] Test migration on Supabase dashboard
- [ ] Update backend Pydantic models (`MatchGroupPayload`, `TopicUpdate`)
- [ ] Update frontend types (`MatchGroup`, `TimelineCell`, `TopicData`, `TimelineTopic`)
- [ ] Update `seed_defaults()` to include `not_discussed_check` artifact type

## Dev Tests
- Run migration, verify columns exist via SQL query
- Insert/query with new column types
- Verify existing `topic_match_groups` data migrated correctly
