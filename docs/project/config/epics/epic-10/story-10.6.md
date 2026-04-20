# Story 10.6 — Implement Prompt Fixes From Audit

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.6, §6 Phase 5
**Depends on:** 10.2 (audit doc must be complete and user-approved before this story starts)

---

## Goal
For every recommended fix identified in `epic-10-prompts-audit.md`, either implement the fix or record an explicit deferral with rationale. Each fix is its own commit and its own test. The audit doc is updated as the source of truth for what was shipped and what was deferred.

## Expected fixes (subject to audit confirmation — may shrink or expand)

| # | Prompt | Expected fix | Test to write first (fails before fix) |
|---|---|---|---|
| 6.1 | Call Topics Extraction | Pass existing project topic vocabulary (names only, not full data) so new call topics align with prior naming | Extraction on Call 2 with an existing "API design" topic → new call topic uses "API design" not a near-synonym |
| 6.2 | Project Topics Merge (auto-match) | Include historical `transcript_excerpt` per existing topic (via lineage helper) so the match prompt sees evidence, not just summaries | Matching a semantic-equivalent call topic to an existing one succeeds based on excerpt content |
| 6.3 | Per-topic Merge (CRITICAL RULES) | Already solved by Story 10.1 — confirm no additional changes needed | Lineage-aware merge test (already in 10.1) |
| 6.4 | Merge Verification | Feed ancestor-call transcripts/excerpts (via lineage helper) so the verifier catches dropped commitments from pre-merge ancestor calls | Call-3 verification of an M:N-merged topic catches a dropped follow-up from Call 1 |
| 6.5 | Not-Discussed Verification | Include prior-call excerpts for this topic so the verifier distinguishes "never-discussed-this-call" from "stale commitment that was closed earlier" | Verifier reasoning references prior-call context when deciding "still pending" vs "resolved earlier" |
| 6.6 | Artifacts (project scope) | Pass full `topic_updates` history via lineage helper so project-scope artifacts can narrate evolution, not only current state | Executive Summary for a 3-call project cites per-call evolution not just final state |

## Acceptance Criteria
- [ ] Every row in the audit is either: (a) implemented and marked "implemented — commit {sha}", or (b) deferred and marked "deferred — reason: {rationale}"
- [ ] Each implemented fix has a failing test written before the code change (TDD)
- [ ] Each implemented fix is a discrete commit with a descriptive message
- [ ] Token-budget observation is re-measured after each fix; if a fix pushes a prompt near or over a practical limit (e.g., 20k tokens), the fix is revised to use compression (summarisation of older evidence) or deferred
- [ ] The audit doc is updated (post-Story) to reflect final status of every recommendation
- [ ] All Epic 9 + Story 10.1 tests still pass

## Tasks
- [ ] Re-read audit doc; for each recommendation, open a child task
- [ ] For 6.1: implement extraction vocabulary pass + test
- [ ] For 6.2: implement match-prompt excerpt inclusion + test
- [ ] For 6.3: confirm no additional work needed; document in audit
- [ ] For 6.4: implement merge-verification ancestor-transcripts + test
- [ ] For 6.5: implement not-discussed verification prior-context + test
- [ ] For 6.6: implement artifacts project-scope lineage inclusion + test
- [ ] Update `epic-10-prompts-audit.md` status column for each row
- [ ] Run full test suite; fix any regressions
- [ ] Manual QA: run the full pipeline on a 3-call seeded project and inspect every prompt's log output to confirm richer context

## Dev Tests
- Before each fix, write a failing test that exhibits the blindness the audit identified
- After each fix, the test passes; run full suite to confirm no regressions
- For token-budget: capture prompt character count in logs before and after each fix; confirm no fix silently balloons the prompt

## Out of Scope
- New prompt categories
- Changes to `artifact_types` schema (category constraint is already flexible)
- Reworking the not-discussed verification to run in parallel for all topics (current sequential behavior retained unless audit flags it)
