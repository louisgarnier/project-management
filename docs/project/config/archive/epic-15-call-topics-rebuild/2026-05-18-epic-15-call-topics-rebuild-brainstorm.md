# Brainstorm — EPIC-15: Call Topics Rebuild

**Status:** `[x] GO — Proceed to PRD`
**Date:** 2026-05-18
**Branch:** `epic-15-call-topics-rebuild`
**Lodestars (read these first):**
- Reference output the new prompt must beat: `/Users/louisgarnier/Downloads/FactSet_SWIB_RAM_Tracker_v04.xlsx` (used only for topic quality benchmarking — no xlsx work in this epic)
- Approved UI: `call-topic-tile-v3.html` (rendered in the local mockup server on 2026-05-18). Stored in `.superpowers/brainstorm/.../content/` (gitignored). Re-render any time via `ui-mockup` skill before build.

---

## One-line goal
Replace today's verbose, drifting call-topics output with sharp, evidence-anchored topics that map to clear `tasks[]`, surfaced in a row-per-task UI with full inline editing.

## Why now
Today's call-topics extraction (EPIC-11) produces over-detailed topics that drift from what was actually said. The 3-section coloured tile (Decisions / Actions / Open questions) is harder to scan than a flat task table and doesn't lend itself to downstream re-use. Rebuilding the prompt + storage shape + UI is the smallest change that fixes both.

## Scope (locked — every item is contract, no improvisation)

This epic touches the **Call Topics stage only**. No change to project-matching, no change to any downstream stage's input contract, no xlsx work, no artifact rebuild, no per-call markdown export change.

### Data model — what the prompt produces per topic
```
{
  name: string,                                          // required, short + synthetic
  importance: "high" | "medium" | "low",                 // required
  key_terms: string[],                                   // required, ≥1, no upper limit
  evidence: [                                            // required, ≥1 references
    { speaker: string, quote: string, citation: string }
  ],
  tasks: [                                               // required, ≥1
    {
      task: string,                                      // required, short
      next_step: string,                                 // required, longer
      status: "open" | "in_progress" | "resolved",       // required
      owner: string                                      // optional (empty allowed)
    }
  ]
}
```
- A topic without ≥1 evidence reference AND ≥1 task is **invalid** — extraction rejects it.
- Status lives **only** on each task, not on the topic.
- Evidence citation format: `"transcript {call_date} · lines {start}-{end}"` (best-effort line range).

### Prompt (`backend/prompts/call_topics.py`) — rewrite
- Output schema locked to the JSON above.
- Drop from contract: `decisions[]`, `follow_up_items[]`, `open_questions[]`, `rationale`, `is_parked`, and the existing topic-level `owner` enum (Us / Client / Both).
- Rubric rewritten with the explicit goal: **short, synthetic, real topics**. Reject padding, drift, speculation. Every topic justified by ≥1 verbatim quote. Today's failure mode (over-detailed, drifting) is named in the rubric as the anti-pattern.
- `key_terms` instructed: produce as many anchoring terms as the topic supports — acronyms, proper nouns, distinctive phrases. No cap.
- No prompt-side ordering by importance; UI renders in prompt order.

### Backend
- New DB migration on `topic_updates`: add `evidence JSONB`, `key_terms JSONB`, `tasks JSONB`. Drop or stop writing `decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, `owner` (the old topic-level enum). Exact drop strategy locked at Architecture step.
- `backend/services/topics_service.py`: update `_TOPIC_SCHEMA`, `TopicIn`, `TopicOut`; update `extract_call_topics` parser to validate the new shape (reject topics without evidence or tasks); update inline-edit endpoints to support per-task task / next_step / owner / status edits, per-task add / delete, per-topic edits (name, importance, key_terms, evidence), and per-topic delete.
- `backend/routers/topics.py`: aggregate endpoint preserves its current output contract to the next stage. Anything from call topics flows downstream unchanged in shape (next stage is manual — no prompt or code change there).
- `backend/services/export_service.py` (per-call markdown): untouched in this epic.
- **Rollback semantics preserved verbatim**: re-running call_topics extraction on call N rolls back later calls to the call_topics stage. This epic adds a regression test on the 4-FactSet-transcript fixture covering this exact path.

### Frontend
- `frontend/src/types.ts`: reshape `TopicData` to the new schema; remove old list fields.
- `frontend/src/components/CallTopicsStage.tsx`: replace the EPIC-11 `SectionBlock` tile with the v3 layout — flat table, topic name + chips repeated on every task row, columns `Topic / chips | Task | Next step | Owner | Status | Evidence | Actions`. One row per task. No row-grouping continuation marker (v2's "↳ same topic" is rejected).
- Inline editing (all fields): topic name, importance dropdown, key_terms (add / remove chips), evidence (add / remove / edit references), task text, next_step text, owner text, status dropdown, add task, delete task, delete topic. Every edit persists via the topic service.
- Evidence interaction: hover the 📄 indicator → styled popover (white background, soft border, one block per reference, speaker bold + quote italic + citation small grey). Not the native browser tooltip.
- `TopicEditor.tsx`, `TopicEvidenceDrawer.tsx`, `TopicsDashboard.tsx`, `TopicsPanel.tsx`: prune removed fields, render new fields.
- `frontend/src/api/client.ts`: type updates only.

## Acceptance criteria — locked
1. Real-fixture test (`backend/tests/test_real_fixture_4calls.py`) runs end-to-end with the new prompt + new UI on the smoke-test project (`17e2687f-bdd8-43ee-88a7-d2bd79a13925`). Per-CLAUDE.md mandatory testing rule applies.
2. Every topic extracted from the 4 FactSet transcripts carries ≥1 evidence reference and ≥1 task. Topics are visibly tighter than today's EPIC-11 output.
3. Extract tile renders the v3 layout exactly: one row per task, topic + chips repeated on every row, evidence as styled hover popover.
4. Every editable field can be changed inline and persisted; status dropdown works; add / delete task works; delete topic works; chip add / remove works.
5. Rollback regression test passes: re-run call_topics on call 2 → calls 3 and 4 roll back to call_topics stage.
6. Project matching (next manual stage) consumes the new topic records without code changes downstream.

## Non-goals (LAW — do not implement in this epic)
- xlsx export of any kind.
- Decisions log, status review, chronology, key-terms registry — none.
- Per-call markdown export changes.
- Artifact-pipeline changes of any kind.
- Project-matching stage changes (input contract, prompt, UI).
- Owner roster / people management.
- Backfill or migration of existing topic_updates rows. Forward-only; old rows readable through their old fields until purged.
- Empty-tasks handling — a topic with zero tasks is rejected at extraction; no empty-state UI.

## Open questions for PRD / Architecture
1. Drop strategy for the old columns (`decisions`, `follow_up_items`, `open_questions`, `rationale`, `is_parked`, topic-level `owner`) — DROP at migration time, or stop writing and DROP in a follow-up cleanup? Same call topics stage may briefly read them during migration window.
2. Editor / drawer components currently read the old fields — best path: collapse into the new flat table component and delete the standalone editor drawer, or refactor to consume new schema?
