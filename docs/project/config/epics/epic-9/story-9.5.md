# Story 9.5 — Not-Discussed Verification Backend + UI

**Epic:** EPIC-9 — M:N Topic Merge + Not-Discussed Verification
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-9-mn-merge-and-verification-design.md` §3
**Depends on:** Story 9.1

---

## Goal
Automatically verify not-discussed topics against the call transcript. Flag topics that were actually discussed. Allow the user to promote flagged topics into the merge pipeline.

## Acceptance Criteria
- [ ] `verify_not_discussed_topics()` runs as background task after `save_match_groups` advances to project_updates
- [ ] Each not-discussed topic is checked against the call transcript using the `not_discussed_check` workflow prompt
- [ ] Results stored in `calls.verification_cache` (keyed by topic_id)
- [ ] `calls.verification_status` tracks progress: idle → processing → done/failed
- [ ] `POST /calls/{call_id}/topics/verify-not-discussed` endpoint triggers verification
- [ ] ProjectUpdatesStage polls `verification_status` alongside `merge_status`
- [ ] Flagged topics show "⚠ Discussed in call" badge with LLM reasoning
- [ ] Confirmed not-discussed topics show "✓ Confirmed" badge
- [ ] "Promote to Updated →" button moves flagged topic to Needs Merge section
- [ ] Promoted topics can go through the merge workflow

## Tasks
- [ ] Write `verify_not_discussed_topics()` in `topics_service.py`
- [ ] Write `run_verification_background()` wrapper (same pattern as `run_merge_background`)
- [ ] Add `POST /calls/{call_id}/topics/verify-not-discussed` endpoint in `routers/topics.py`
- [ ] Add verification trigger in `save_match_groups()` (background task)
- [ ] Update `ProjectUpdatesStage.tsx`: poll verification_status, render badges
- [ ] Add "Promote to Updated →" button with state management
- [ ] Update `calls.py` router to return verification fields

## Dev Tests
- Backend test: verification detects discussed topic → `discussed: true` in cache
- Backend test: verification confirms not-discussed → `discussed: false` in cache
- Backend test: verification handles LLM errors gracefully (status=failed, non-fatal)
- Frontend: flagged badge appears on discussed topic, promote button works
- Frontend: confirmed badge appears on genuinely not-discussed topic
- Integration: promote topic → run merge → topic appears in Updated Topics section
