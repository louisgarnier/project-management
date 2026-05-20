# PRD — Epic 7: Topics Refactor + Timeline Grid

**Status:** Draft  
**Date:** 2026-04-13  
**Author:** Louis Garnier

---

## Problem

The current topics extraction pipeline is biased. When extracting topics for Call 2+, the LLM receives both the transcript AND the full list of previous project topics in the same prompt. This causes the LLM to:
- Force-fit new discussions into existing topic names even when they're different
- Create "ghost" follow-ups for topics that were barely or never mentioned
- Miss genuinely new topics because it's anchored on the previous list

Additionally, there is no visual overview showing how topics have evolved across all calls — the board's Topics tab shows only a flat snapshot, not a timeline.

---

## Goals

1. **Extraction quality**: Each call's topics are extracted cleanly from the transcript only, without bias from previous context.
2. **Accurate aggregation**: A dedicated second step matches the clean call topics against accumulated project topics, with the user able to correct missed matches.
3. **Richer artifacts**: Artifact generation has access to the full project topic state, not just the current call's transcript.
4. **Topic timeline**: The board's Topics tab shows a grid of all topics × all calls, giving a full history of how each topic evolved.

---

## Non-Goals

- No changes to transcript upload or transcription server
- No changes to artifact type management
- No changes to the lock/stale mechanism (Epic 6)
- Manual topic entry (add topic without extraction) continues to work as-is

---

## New Kanban Flow

```
Transcript → Call Topics → Project Topics → Artifacts → Done
```

| Stage | What happens |
|---|---|
| `transcript` | Upload/edit transcript (unchanged) |
| `call_topics` | LLM extracts topics from this call's transcript only — no previous context |
| `project_topics` | LLM matches call topics against accumulated project topics → 3-bucket review |
| `artifacts` | Generate artifacts with full project topic context |
| `done` | Call complete (unchanged) |

Replaces the old single `topics` stage.

---

## Epic 7A — Two-Step Extraction + New Kanban Stages

### User Stories

**Story 7A.1 — DB Migration: new stage values**

As a developer, I need the `kanban_stage` column to support `call_topics` and `project_topics` so the new flow can be enforced at the DB level.

Acceptance criteria:
- `kanban_stage` CHECK constraint updated: `('transcript', 'call_topics', 'project_topics', 'artifacts', 'done')`
- All existing rows at `topics` stage migrated to `call_topics`
- All existing rows at other stages unchanged
- Backend `STAGE_ORDER` updated: `['transcript', 'call_topics', 'project_topics', 'artifacts', 'done']`
- All backend tests passing after migration

---

**Story 7A.2 — Step 1: Call Topics extraction endpoint**

As a user, I want to extract topics from the current call's transcript only, so the extraction is unbiased by previous calls.

Acceptance criteria:
- `POST /calls/{id}/topics/extract_call` extracts a flat list of topics using the transcript only — no previous project topics in the prompt
- Identical extraction logic to current Call 1 extraction
- Returns flat list: `[{name, summary, follow_up_items, decisions, status, owner, sentiment}]`
- Does NOT save to DB, does NOT advance stage
- Returns 404 if call not found, 422 if no transcript
- Backend test covers happy path and no-transcript guard

---

**Story 7A.3 — Step 2: Aggregate endpoint**

As a user, I want the extracted call topics matched against accumulated project topics, so I can see what was followed up, what was new, and what wasn't discussed.

Acceptance criteria:
- `POST /calls/{id}/topics/aggregate` accepts a flat list of call topics from the frontend
- Backend fetches accumulated project topics (name + summary + follow_up_items from latest update per topic) for LLM context
- LLM Call 2 prompt: "here are this call's extracted topics, here are the project's existing topics with their history — classify into followed_up / not_discussed / new_topics"
- For **Call 1** (no previous project topics): backend skips LLM Call 2, saves all topics as new, advances stage to `artifacts`, returns `{"auto_advanced": true}`
- For **Call 2+**: returns 3-bucket result `{call_number, followed_up, not_discussed, new_topics}` — does NOT save to DB yet
- `_reattach_id` logic applied (same as current) so followed_up topics carry their topic_id
- Backend tests: Call 1 auto-advance, Call 2+ 3-bucket return, 404 guard

---

**Story 7A.4 — Call Topics UI (call_topics stage)**

As a user, I want to review the flat list of topics extracted from the current call before aggregating them with the project.

Acceptance criteria:
- New `CallTopicsStage` component replaces the current `TopicsStage` for the `call_topics` kanban stage
- On mount: shows "Extract this call's topics" button
- On extract: calls Step 1 endpoint, shows flat list of topic cards (name, summary, follow_ups, status, owner, sentiment — all editable)
- User can edit any field on any topic card
- "Continue →" button sends the (possibly edited) flat list to the Step 2 aggregate endpoint
- For Call 1: backend returns `auto_advanced: true` → frontend shows brief "Topics saved as project baseline" message → reloads call → advances to `artifacts` stage automatically
- For Call 2+: advances the call to `project_topics` stage, redirects to that stage's page
- Loading and error states handled

---

**Story 7A.5 — Project Topics UI (project_topics stage)**

As a user, I want to review how this call's topics relate to the project's existing topics, and manually correct any missed matches.

Acceptance criteria:
- New `ProjectTopicsStage` component for the `project_topics` kanban stage
- On mount: auto-runs aggregate endpoint with the call topics already saved in state (or re-triggers if state lost — Step 1 is re-run silently)

  > **Implementation note:** since Step 1 result is held in frontend state, if the user navigates away and back, Step 1 must be re-run silently before showing Step 2. The aggregate endpoint accepts any flat list so this is straightforward.

- Shows 3-bucket view: Followed Up / Not Discussed / New Topics
- **"Link to existing" on new topic cards**: button opens a searchable dropdown of existing project topics; selecting one moves the card to Followed Up bucket with the existing topic's `topic_id`
- User can still edit all fields on any topic card
- Validate button: calls `POST /calls/{id}/topics/validate`, saves all topics, advances to `artifacts`
- Validate disabled until all not_discussed topics have a disposition (keep / archive) — same rule as today
- Loading, error, and empty states handled

---

**Story 7A.6 — Artifact generation: inject project topic context**

As a user, I want artifact generation to have access to the full project topic state so the outputs are grounded in the overall project history, not just this call.

Acceptance criteria:
- When generating artifacts, the backend appends a compact project topics summary to the LLM prompt context
- Summary format: list of open/in_progress topics with name, latest summary, open follow-up items (max 3 per topic)
- Resolved topics excluded from the summary
- No change to artifact type prompts required — the context is appended automatically
- Existing artifact generation tests still pass

---

### Out of scope for 7A
- Timeline grid (Epic 7B)
- Changes to TopicsPanel on done calls (historical view)
- Changes to PreCallBrief

---

## Epic 7B — Topics Timeline Grid

### User Stories

**Story 7B.1 — Timeline backend endpoint**

As a developer, I need an endpoint that returns the full topic × call matrix so the frontend can render the grid without computing anything.

Acceptance criteria:
- `GET /projects/{id}/topics/timeline` returns:
  ```json
  {
    "calls": [{"id", "title", "number", "kanban_stage"}],
    "topics": [{
      "topic_id", "name", "status", "owner", "sentiment",
      "first_raised_call_id",
      "call_updates": {
        "<call_id>": {"type": "new|followed_up|not_discussed", "summary", "follow_up_items", "decisions", "status", "owner", "sentiment"}
        // absent key = topic did not yet exist at this call
      }
    }]
  }
  ```
- Topics with no remaining updates (orphans) excluded
- Backend test covers: empty project, new + not_discussed cells, followed_up + absent cells

---

**Story 7B.2 — Timeline grid UI**

As a user, I want to see a grid of all topics × all calls on the Board's Topics tab so I can understand how each topic evolved across the project.

Acceptance criteria:
- Board → Topics tab renders `TopicsTimeline` component (replaces `TopicsDashboard`)
- Rows = topics (fixed left column: name + current status/owner/sentiment badges)
- Columns = one per call (header: "Call N" + call title truncated)
- Grid scrolls horizontally for many calls
- Cell states:
  - **Empty** (topic post-dates this call): blank cell
  - **Not discussed**: grey "—"
  - **New ✦**: orange badge + truncated summary (2 lines max)
  - **Updated**: blue badge + truncated summary + follow-up count
  - **✓ Resolved**: green badge
- Resolved topic rows shown at 65% opacity
- Empty state when no topics exist yet

---

## Sequencing

```
7A.1 (DB migration)
  → 7A.2 (Step 1 endpoint)
  → 7A.3 (Step 2 aggregate endpoint)
  → 7A.4 (Call Topics UI)
  → 7A.5 (Project Topics UI)
  → 7A.6 (Artifact context)
  → 7B.1 (Timeline endpoint)
  → 7B.2 (Timeline UI)
```

7A must be fully complete before 7B is built, so the timeline grid reflects clean data from the two-step extraction.

---

## Data Model (unchanged)

No new tables required. The existing schema handles everything:
- `calls.kanban_stage` — updated constraint only
- `topics` — unchanged
- `topic_updates` — one row per topic per call, unchanged
- `artifacts` — unchanged

---

## Open Questions

- None — all design decisions resolved in brainstorm session 2026-04-13.
