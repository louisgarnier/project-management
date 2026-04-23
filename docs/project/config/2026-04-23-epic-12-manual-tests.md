# EPIC-12 Manual Test Walkthrough

**Date:** 2026-04-23
**Branch:** `epic-12-artifacts-overhaul`
**Estimated time:** 20–30 min

This doc is a checklist. Walk the 6 phases in order. Each step is a single `[ ]` checkbox to tick. Known non-goals + pre-existing backend test failures listed at the bottom.

---

## Phase A — Pre-flight (once)

### A.1 — Migration 021
- [ ] Open Supabase SQL editor
- [ ] Paste `backend/database/migrations/021_artifact_library.sql` and run it
- [ ] Verify `artifact_types` now has columns `kind`, `template_id`, `library_ref_id`
- [ ] Verify `artifact_library` table exists with 11 columns

### A.2 — Backend startup seeds library
- [ ] Restart the backend: `cd backend && uvicorn backend.main:app --reload`
- [ ] In backend log, look for: `✅ [Startup] artifact_library seeded: inserted=8 preserved=0` (first boot) or `inserted=0 preserved=8` (subsequent boots)
- [ ] In Supabase Table Editor, verify 8 rows in `artifact_library`: Executive Summary, Next Steps & Action Items, Questions for Stakeholders, Email Summary (1-pager), Email Follow-up (pre-next-call), Next Call Agenda, Risk Register, Decisions Digest
- [ ] 3 should have `seeded_by_default=true` (Exec Summary, Next Steps, Questions)
- [ ] All 8 should have `is_system=true`

---

## Phase B — Existing project unchanged

- [ ] Navigate to `/projects/<your-aaaa-project-id>/artifacts`
- [ ] Verify Tier 1 section shows **4 cards** — including the previously-hidden `merge_verification` and `not_discussed_check` prompts
- [ ] Verify Tier 2 section shows your existing artifact types (should be the 6 from before, or however many you had)
- [ ] Each existing Tier 2 card should show its kind tag and (if it matches a system library name) a `⟲ canonical` or `✎ edited` badge

### B.1 — Reset existing LLM Next Steps to template kind
- [ ] Click Edit on the "Next Steps & Action Items" card
- [ ] Click "⟲ Reset to default" (should fall back to system library by name match)
- [ ] Confirm dialog
- [ ] After save, card should switch: no prompt textarea, description + Preview button + "Cost: $0 (template)"
- [ ] Run generation on a call — Next Steps output should match the `follow_up_items[]` visible on the Call Topics tiles

---

## Phase C — New project

- [ ] Create a fresh new project
- [ ] Navigate to `/projects/<new>/artifacts`
- [ ] Verify Tier 1 section has 4 cards (4 workflow prompts)
- [ ] Verify Tier 2 section has exactly 3 cards: Executive Summary 🤖, Next Steps 🔧, Questions 🔧
- [ ] NO Email Summary, NO Email Follow-up, NO Agenda, NO Risk Register, NO Decisions Digest (opt-in via library)

---

## Phase D — Library flow

### D.1 — Add from library
- [ ] Click "+ Add artifact type" → modal opens with "Browse library" tab default
- [ ] Verify 5 system entries visible: Email Summary, Email Follow-up, Next Call Agenda, Risk Register, Decisions Digest
- [ ] Click Add on "Email Summary (1-pager)"
- [ ] Modal closes, Tier 2 now shows Email Summary

### D.2 — Publish custom artifact to library
- [ ] In the modal, switch to "Create new" tab
- [ ] Create a custom artifact, e.g. "Board Meeting Summary" with prompt "Write a board-style summary of this call"
- [ ] On its card, click "↗ Publish to library"
- [ ] Fill name + one-line description, click Publish
- [ ] Page reloads, card now has `⟲ canonical` badge
- [ ] Open `/library` in sidebar → see it under "👤 Yours"

### D.3 — Edit a library entry
- [ ] On `/library`, click Edit on your just-published entry
- [ ] Change description, click Save
- [ ] Reload → edit persisted

### D.4 — Delete a user entry
- [ ] Click Delete on your user entry → confirm
- [ ] Entry gone from library

### D.5 — Can't delete system entries
- [ ] Try to find a Delete button on a system library entry (e.g. Risk Register)
- [ ] Delete button should be HIDDEN
- [ ] (Backend-only test: hitting `DELETE /api/library/<system-id>` returns 403)

### D.6 — Reset system library
- [ ] Edit a system entry (e.g. change Risk Register's description)
- [ ] Save
- [ ] Click "⟲ Reset system to defaults" at the top of the System section
- [ ] Confirm → your edit should revert

---

## Phase E — Generation flow

Run artifact generation on a call that has Exec Summary 🤖 + Next Steps 🔧 + Questions 🔧:

- [ ] Watch backend logs during generation
- [ ] Executive Summary fires LLM: `🤖 [OpenRouter/anthropic/claude-sonnet-4.6] Generating artifact`
- [ ] Next Steps generates WITHOUT an LLM call: `✅ [DB] Artifact done (template): <id>`
- [ ] Questions also generates without LLM
- [ ] In the frontend, Next Steps output is markdown with `## <topic>` headers and `- **Nick:** run benchmark` bold-prefix format
- [ ] Questions output shows `- <question>` grouped by topic
- [ ] Add "Next Call Agenda" from library → regenerate
- [ ] Logs show hybrid: template render + 2 LLM calls (intro + closing)
- [ ] Output has: 1 intro sentence + template bullet list + 1 closing sentence

---

## Phase F — Cost verification

- [ ] On any LLM kind card, click Edit → near the model picker, verify "Cost estimate: ~$0.10" (for Sonnet 4.6) or "~$0.008" (for DeepSeek)
- [ ] Template cards show "Cost: $0 (template)"
- [ ] Hybrid card (Next Call Agenda) shows "Cost: ~$0.0XX (2 short LLM calls)"

---

## Known non-goals

- No user-editable template logic (templates require Python code)
- No cascading library edits: editing a library entry does NOT propagate to projects that already added it (copy semantics)
- No live pricing API (MODEL_COSTS is a hardcoded frontend constant)
- No versioned prompt history
- No multi-user / multi-org library scoping

## Pre-existing backend test failures (unrelated to EPIC-12)

- `test_delete_default_type_forbidden`
- `test_seed_defaults_inserts_topics_prompt`
- `test_list_artifacts_for_call`
- `test_patch_stage_project_topics_to_artifacts`
