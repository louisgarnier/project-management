# Story 9.4 — M:N Merge Pipeline + RAG Synthesis Backend

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §2.3, §2.4, §2.5
**Depends on:** Story 9.1, 9.2

---

## Goal
Refactor the backend merge pipeline to handle M:N groups. Build RAG-style merge prompts that pull transcript excerpts from all historical topic_updates. Handle topic archival when M:N merges create new combined topics.

## Acceptance Criteria
- [ ] `save_match_groups()` accepts `project_topic_ids: list[str]` per group
- [ ] `run_merge_preview()` handles 3 group types:
  - Empty `project_topic_ids` + multiple call topics → merge into 1 new topic (LLM-proposed name)
  - Single `project_topic_ids` + call topics → update existing topic (current behavior)
  - Multiple `project_topic_ids` + call topics → merge all into 1 new topic (LLM-proposed name, `_source_topic_ids` set)
- [ ] Merge prompt includes transcript excerpts from all historical `topic_updates` for each source topic
- [ ] Merge prompt includes transcript excerpts from current call topics
- [ ] Merged result includes `_source_topic_ids` for multi-topic groups
- [ ] `validate_project_updates()` handles archival: sets `merged_into_topic_id` and `archived=True` on source topics
- [ ] Single-topic groups (1:N match) continue to update in place (no archival)
- [ ] `_source_topic_ids` stripped before DB persistence

## Tasks
- [ ] Update `save_match_groups()` to use `project_topic_ids` array
- [ ] Add `_load_transcript_excerpts(topic_id)` helper: returns all excerpts ordered by call date
- [ ] Refactor `merge_one()` for 3 group types with RAG-style prompts
- [ ] Update `validate_project_updates()` archival logic for `_source_topic_ids`
- [ ] Update `run_merge_preview()` not-discussed list to handle multi-topic groups
- [ ] Update `MatchGroupPayload` in `routers/topics.py`

## Dev Tests
- Backend test: 2 existing topics + 2 call topics → 1 merged output with proposed name
- Backend test: 3 call topics as new → 1 merged output with proposed name
- Backend test: 1 existing + 1 call → updated existing (regression)
- Backend test: validate with `_source_topic_ids` → source topics archived, `merged_into_topic_id` set
- Backend test: transcript excerpts present in merge prompt (mock LLM, inspect prompt)
