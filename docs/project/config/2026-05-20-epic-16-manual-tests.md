# EPIC-16 Manual Test Plan

**Date:** 2026-05-20  
**Branch:** epic-16-rag-rework  
**Migration:** 030 (must be applied manually via Supabase Dashboard before backend restart)

## Pre-requisites

- [ ] Migration 030 applied to Supabase (file: `backend/database/migrations/030_epic16_rag_passes.sql`)
- [ ] Backend restarted — confirm via logs that startup seeds the 3 new system library entries (`verify_new_topic`, `verify_not_discussed`, `extract_topic_updates`)
- [ ] Project's default LLM is set to a model with adequate context (Claude Sonnet 4.6 1M recommended). Verify via Settings or `projects.default_llm` directly.

## Scenario A — Typical Call 2 (followed-up + new + not-discussed)

1. Create a fresh project "EPIC-16 smoke" with default_llm = openrouter + default_model = anthropic/claude-sonnet-4-6.
2. Upload a Call 1 transcript (a ~5k-token document with 3+ distinct topics). Run call_topics → advance to artifacts.
3. Upload a Call 2 transcript that mentions 2 of Call 1's topics + introduces 1 new topic.
4. At project_matching: link the 2 followed-up topics, mark the new topic as New, leave 1 topic from Call 1 unmatched.
5. Click "Save & Continue".
6. **Expectation: No background LLM call fires.** Verify in logs that no `[verify_*]` or `[extract_*]` log lines appear between save_matches and the user clicking ① on project_updates.
7. On project_updates page, confirm the 3-section layout:
   - Section 1 "New topics from this call" — 1 card
   - Section 2 "Old topics not in this call" — 1 card (greyed out, button disabled)
   - Section 3 "Merged topics" — 2 cards with side-by-side previous/this-call data (greyed out, button disabled)
8. Click ① "Verify new". Spinner appears. Other buttons remain disabled.
9. Wait for ✓ done badge on Section 1 header. Confirm:
   - The new topic card shows "✓ truly new" badge OR — if the LLM thinks it should be merged — "↻ moved to merged" and the card disappears from Section 1, reappearing in Section 3 with "moved from New" badge.
10. Click ② "Verify not discussed". Spinner appears. Section 3 button remains disabled.
11. Wait for ✓ done badge on Section 2 header. Confirm:
    - The not-discussed card shows "✓ not discussed" badge OR "↻ actually discussed — moved to merged" if LLM finds a mention.
12. Click ③ "Extract updates". Spinner appears. Wait for ✓ done badge on Section 3 header.
13. Confirm each merged topic card displays:
    - Extracted snapshot summary
    - Tasks list (each task derived from transcripts)
    - Evidence trail at the bottom showing chronological per-call citations
14. Click "Save & Continue → Artifacts". The call advances to artifacts stage.
15. Open the Topics tab → Timeline. Click the topic name → drawer opens (or inline view), confirm the new topic_update for Call 2 carries the evidence_trail and citations.

## Scenario B — Pass ① promotes a missed match

1. At call_topics for a Call 2, deliberately extract a topic whose name resembles an existing Call 1 topic but with different wording (e.g., "Mac issue" vs an existing "MC Mac memory issue").
2. At project_matching, do NOT link it — mark it as new.
3. On project_updates, click ①.
4. Expected: the new topic migrates from Section 1 to Section 3 with badge "moved from New".
5. Click ② then ③. The migrated topic gets a full extraction in Section 3.

## Scenario C — Citation failure → needs_manual_review

1. Use a Call with a short / quirky transcript that's likely to confuse the LLM into hallucinating quotes.
2. Run ① (or ③) — observe whether the retry path triggers. Look for log lines like `[verify_new] citation verify failed on attempt 1: ...`.
3. If retry's second attempt ALSO fails verification, the topic should display "⚠ needs manual review" badge on its card.
4. After Save & Continue, confirm `topic_updates.needs_manual_review = true` for that row in DB (or use Topics Timeline view — cell should show ⚠️ icon).

## Cleanup

After testing, delete the smoke project. Confirm cascade deletes all topics + topic_updates + calls.

## Rollback test

1. Reach project_updates stage with all 3 passes ✓ done. Save & Continue → artifacts.
2. Rollback to project_matching.
3. Confirm: match_groups preserved, the 3 verify caches/statuses are cleared (reset to idle).
4. Rollback further to call_topics.
5. Confirm: extraction_cache restored, 3 verify caches still idle, pending_topics cleared.
