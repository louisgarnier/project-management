# EPIC-11 — Call Topics Extraction Overhaul: Consolidated Manual Test Doc

**Date:** 2026-04-22
**Branch:** `epic-11-call-topics-overhaul`
**Estimated walk-through time:** 20–30 minutes

---

## How to read this

This document is a single, linear checklist covering the entire EPIC-11 surface.
Work through it top-to-bottom in one sitting; **order matters**.

- **Phase A** sets up the environment — nothing in B–E works without it.
- **Phase B** confirms the Artifacts page UI is correct before any live LLM call.
- **Phase C** validates a live extraction end-to-end using the real OpenRouter API.
- **Phase D** is the quality gate — evaluate 2–3 calls and judge output quality.
- **Phase E** confirms the new fields ripple correctly to every other topic surface.

Mark each `[ ]` checkbox as you complete the step.

---

## Phase A — Environment setup (one-time, pre-flight)

### A.1 — API key

- [ ] Open `backend/.env`
- [ ] Confirm `OPENROUTER_API_KEY=<your-key>` is present (get a key at https://openrouter.ai/keys if not)
- [ ] Restart the backend if it was already running: `cd backend && uvicorn backend.main:app --reload`

### A.2 — Run migration 019

- [ ] Open the Supabase SQL editor for this project
- [ ] Paste the contents of `backend/database/migrations/019_call_topics_overhaul.sql` and run it
- [ ] Verify in the Supabase Table Editor that:
  - [ ] `topic_updates` has columns: `open_questions` (jsonb), `is_parked` (bool), `importance` (text), `rationale` (text)
  - [ ] `artifact_types` has column: `model` (text, nullable)
  - [ ] `projects` has column: `default_model` (text, nullable)

### A.3 — Run the prompt migration script

- [ ] In a terminal, **from the repo root** (not from inside `backend/`): `python3 -m backend.scripts.migrate_call_topics_prompt`
- [ ] Confirm the output is: `Done. Migrated: N, Preserved: M.` (N ≥ 0, M ≥ 0, no errors)
- [ ] "Migrated" = rows that had the old unedited default prompt, now updated to the new rubric-driven default
- [ ] "Preserved" = rows the user had customized — these are left untouched

---

## Phase B — Artifacts page smoke

### B.1 — Project-level provider control

- [ ] Navigate to `/projects/{id}/artifacts` for any project
- [ ] Locate the "Default Provider" row in the project settings section at the top of the page
- [ ] Confirm the dropdown currently shows "OpenRouter ⭐" for newly seeded projects (or whatever was previously saved)
- [ ] Select "OpenRouter ⭐" — confirm a "Default Model" text input appears alongside it
- [ ] Enter a model slug (e.g. `anthropic/claude-sonnet-4.6`) and save
- [ ] Reload the page — confirm the provider + model persisted

### B.2 — Artifact Type Card: provider dropdown

- [ ] Click the `call_topics` artifact type card → "Edit" button
- [ ] Confirm the Provider dropdown shows exactly 6 options:
  - [ ] Inherit (project default)
  - [ ] Groq
  - [ ] DeepSeek
  - [ ] Claude
  - [ ] OpenAI
  - [ ] OpenRouter ⭐

### B.3 — Artifact Type Card: model picker

- [ ] In the same edit view, select "OpenRouter ⭐"
- [ ] Confirm a Model dropdown appears with a curated list:
  - [ ] `anthropic/claude-sonnet-4.6`
  - [ ] `openai/gpt-4o`
  - [ ] `google/gemini-2.5-pro`
  - [ ] `deepseek/deepseek-chat`
  - [ ] `meta-llama/llama-3.3-70b-instruct`
  - [ ] "Custom…" row
- [ ] Select "Custom…" — confirm a free-text input field appears for entering an arbitrary model slug

### B.4 — Prompt textarea controls

- [ ] Confirm the prompt textarea is visible with the current prompt text
- [ ] Click "⤢ Expand" — confirm the textarea grows to ~500px height
- [ ] Click "⤡ Collapse" (or the same button in its toggled state) — confirm it shrinks back to ~120px

### B.5 — Runtime context preview

- [ ] Click "Show runtime context" — confirm a read-only preview expands below the textarea
- [ ] Verify it shows sections for: project context, vocabulary, `_TOPIC_SCHEMA` (JSON schema block), and transcript `{placeholders}`
- [ ] Click again to collapse it

### B.6 — Reset to default

- [ ] Click "⟲ Reset to default"
- [ ] Confirm a confirmation dialog appears (e.g. "Are you sure? This will overwrite your current prompt.")
- [ ] Confirm → verify the prompt textarea is now populated with the full multi-section default (should start with the ROLE block and contain RUBRIC / ANCHORS / FEW-SHOT / PROCESS sections)
- [ ] Save the card
- [ ] Reload the page — verify the new prompt persisted

### B.7 — ArtifactSelector label

- [ ] Navigate to a call that is on the Artifacts stage
- [ ] Open the artifact type selector (the dropdown/list used to choose which artifact type to run)
- [ ] For a `call_topics` type that has `llm=openrouter` and a model set: confirm the label shows the provider + model slug appended (e.g. "Call Topics (OpenRouter / anthropic/claude-sonnet-4.6)")

---

## Phase C — Call Topics stage — live extraction

### C.1 — Project and artifact type setup

- [ ] Pick a test project (e.g. RAMMMM) or create a new one
- [ ] Navigate to its `/projects/{id}/artifacts` page
- [ ] Confirm the `call_topics` artifact type has `llm=openrouter, model=anthropic/claude-sonnet-4.6`
  - If not: edit the card, select OpenRouter, select `anthropic/claude-sonnet-4.6`, reset to default prompt, save

### C.2 — Create a call with a real transcript

- [ ] Create a new call (or use an existing call that hasn't been through EPIC-11 extraction yet)
- [ ] Upload a real transcript — aim for a representative past call, roughly 20–30 minutes of dialogue
- [ ] Advance the call to the "Call Topics" kanban stage

### C.3 — Trigger extraction

- [ ] On the Call Topics stage, click "Extract this call's topics"
- [ ] Observe the backend terminal logs
- [ ] Confirm you see a log line matching: `🤖 [OpenRouter/anthropic/claude-sonnet-4.6] Extracting topics` (or similar)
- [ ] Wait for extraction to complete (may take 30–90 seconds depending on transcript length)

### C.4 — Tile rendering — importance dot

- [ ] Confirm each topic tile has a coloured dot to the left of the topic name
  - Red dot = high importance
  - Amber dot = medium importance
  - Grey dot = low importance
- [ ] Hover over the dot — confirm a tooltip appears showing the `rationale` text from the LLM

### C.5 — Tile rendering — summary

- [ ] Confirm topic summaries are multi-sentence (3–6 sentences)
- [ ] Confirm summaries contain specific details: names, numbers, system names, or deadlines — not generic filler

### C.6 — Tile rendering — anchor sections

- [ ] For a topic with decisions: confirm a grey "Decisions" section appears with bullet items
- [ ] For a topic with actions: confirm an amber "Actions" section appears; owner is bolded where present
- [ ] For a topic with open questions: confirm a blue "Open questions" section appears
- [ ] Confirm sections with no items are hidden (not rendered as empty boxes)

### C.7 — Tile rendering — footer

- [ ] Confirm each tile's footer shows: "📄 Source excerpt ↗" link and inline status / owner / sentiment fields

### C.8 — Edit mode

- [ ] Click the ✎ (edit) button on a tile
- [ ] Confirm textareas appear for: summary, each anchor section's items, status, owner, sentiment
- [ ] Add a new item to one section; remove an item from another; save
- [ ] Confirm changes persist on reload

### C.9 — Parked topic (if present)

- [ ] If the extraction returned any `is_parked=true` topic:
  - [ ] Confirm the tile has a muted/faded border
  - [ ] Confirm a ⏸ PARKED chip is visible in the tile header
  - [ ] Confirm the Actions section is hidden on parked topics
  - [ ] Confirm an "Un-park" button is present; click it and verify the topic transitions to unparked state

---

## Phase D — Quality spot-check

Run 2–3 representative past calls through extraction and evaluate each against these criteria. These are subjective judgements — take notes to compare with pre-EPIC-11 results if available.

### D.1 — Consolidation

- [ ] Are topics meaningfully merged? No near-duplicates in the list
- [ ] No 5-way splits of a single thread of discussion into separate topics
- [ ] Related sub-points grouped under one topic rather than scattered

### D.2 — Summary richness

- [ ] Do summaries contain specific numbers, system names, people, or deadlines?
- [ ] Are summaries multi-sentence (not single-line)?
- [ ] Would the summary help someone who wasn't on the call understand what was discussed?

### D.3 — Anchor separation accuracy

- [ ] Are decisions in the Decisions bucket (not in Actions or vice versa)?
- [ ] Do actions have an owner where one was mentioned?
- [ ] Are open questions genuinely unresolved (not closed items)?

### D.4 — Importance rubric fidelity

- [ ] Hover each importance dot — does the rationale text match the actual importance of that topic?
- [ ] "High" topics (red) should be the most strategically significant items from the call
- [ ] "Low" topics (grey) should be minor notes or FYIs

### D.5 — Parked handling

- [ ] If any "we'll look at this later" discussions occurred: confirm they appear as parked topics
- [ ] Parked topics should not be dropped and should not appear as actionable items

---

## Phase E — Ripple checks + other surfaces

### E.1 — Topics board tab

- [ ] Navigate to `/projects/{id}/board?tab=topics`
- [ ] For a topic that has `open_questions`: confirm the open-question count is visible on the topic card
- [ ] For a topic with `is_parked=true`: confirm the ⏸ PARKED chip appears on the board card

### E.2 — Topic Evidence Drawer

- [ ] Open the Topic Evidence Drawer for a topic that was extracted in Phase C
- [ ] In the per-call cards, confirm Open questions (blue) are displayed alongside Decisions and Follow-ups
- [ ] Confirm the layout doesn't break when a section is empty

### E.3 — TopicEditor (topic detail / board side-panel)

- [ ] Open the topic editor (via the board side-panel or topic detail view)
- [ ] Confirm the Open questions list is visible and editable
- [ ] Confirm a Parked checkbox (or toggle) is visible in edit mode
- [ ] Toggle it and save — confirm the change persists

---

## Known non-goals

The following items are intentionally out of EPIC-11 scope. Seeing them absent is expected, not a bug.

- **Backend evidence endpoint missing open_questions**: `/api/topics/{id}/evidence` does not yet return `open_questions` in the per-call data payload. The UI in the Topic Evidence Drawer degrades gracefully by showing nothing. Wiring this through end-to-end is a follow-up item beyond EPIC-11 scope.

- **4 pre-existing backend test failures**: The following test failures pre-date EPIC-11 and are not caused by this epic's changes:
  - `tests/test_artifact_types.py::test_delete_default_type_forbidden`
  - `tests/test_artifact_types.py::test_seed_defaults_inserts_topics_prompt`
  - `tests/test_artifacts.py::test_list_artifacts_for_call`
  - `tests/test_calls.py::test_patch_stage_project_topics_to_artifacts`

  All 4 fail on `main` as well. They are not regressions from EPIC-11.
