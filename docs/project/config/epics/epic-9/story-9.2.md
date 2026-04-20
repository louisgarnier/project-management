# Story 9.2 — Transcript Excerpt Capture in Extraction

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §2.1
**Depends on:** Story 9.1

---

## Goal
Update the topic extraction prompt to capture `transcript_excerpt` per topic. Store it through the pipeline so merge prompts always have primary-source material.

## Acceptance Criteria
- [ ] `extract_call_topics()` prompt includes `transcript_excerpt` in the schema
- [ ] Extracted topics include `transcript_excerpt` field in `extraction_cache`
- [ ] `transcript_excerpt` flows through `pending_topics` to `topic_updates` table
- [ ] `save_topics()` persists `transcript_excerpt` to `topic_updates.transcript_excerpt`
- [ ] `_TOPIC_SCHEMA` updated to include `transcript_excerpt`
- [ ] `TopicIn` / `TopicUpdate` models updated with optional `transcript_excerpt` field
- [ ] Existing calls without `transcript_excerpt` still work (field is optional/nullable)

## Tasks
- [ ] Update `_TOPIC_SCHEMA` string in `topics_service.py`
- [ ] Update extraction prompt in `extract_call_topics()` to request `transcript_excerpt`
- [ ] Add `transcript_excerpt: Optional[str] = None` to `TopicIn` model
- [ ] Update `save_topics()` to persist `transcript_excerpt` in topic_updates insert
- [ ] Update `_normalize_topic()` to default `transcript_excerpt` to `None`

## Dev Tests
- Run extraction on a test call, verify `transcript_excerpt` present in each topic dict
- Advance call through pipeline, verify `topic_updates` rows have `transcript_excerpt` populated
- Verify old calls without excerpt data still process without errors
