# Story 10.2 — Prompts Audit (Read-Only Documentation)

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.5, §6 Phase 2
**Depends on:** 10.1

---

## Goal
Produce a single committed document that catalogues every LLM prompt in the pipeline, what it currently sees, what it should see, and the concrete recommended fix. This is the input that drives Story 10.6.

## Deliverable
`docs/project/config/epic-10-prompts-audit.md` containing one section per prompt.

## Prompts to audit (6)
1. **Call Topics Extraction** — `backend/services/topics_service.py::extract_call_topics`
2. **Project Topics Merge (auto-match)** — `backend/services/topics_service.py::aggregate_topics`
3. **Per-topic Merge (CRITICAL RULES)** — inline in `backend/services/topics_service.py::save_matches`
4. **Merge Verification** — `backend/services/topics_service.py::_verify_merged_topics`
5. **Not-Discussed Verification** — `backend/services/topics_service.py::verify_not_discussed_topics`
6. **Artifacts** — `backend/services/artifacts_service.py` (both `call` and `project` context scopes)

## Per-prompt section template
- **Source reference:** file path + line number
- **Prompt text source:** hardcoded default vs `artifact_types` stored prompt — quote the current text
- **Input assembly code walk:** exact variables passed into the prompt (e.g., transcript, project_context, topic snapshot, historical excerpts)
- **What the LLM sees today:** bulleted list of fields the prompt actually receives
- **What exists in the DB but is withheld:** fields that could/should be included
- **Call-count dependency:** does the input grow / stay flat / get truncated as N grows?
- **Token-budget observation:** rough character/token count at Call 1, 5, 10, 20 (measured or estimated)
- **Blindness(es) identified:** specific missing context that hurts output quality
- **Recommended fix:** concrete change (e.g., "include historical `transcript_excerpt` via `get_lineage_topic_updates`")
- **Priority:** Must / Should / Could — informs Story 10.6 scope

## Acceptance Criteria
- [ ] `docs/project/config/epic-10-prompts-audit.md` exists and is committed
- [ ] All six prompts covered with every template field populated
- [ ] File and line references resolve to current main branch
- [ ] Each recommended fix is concrete enough to implement without further research
- [ ] Token-budget observations are real measurements (capture prompt length in logs on a recent call) or explicitly labelled "estimate"
- [ ] Top-level summary table lists all six prompts with one-line recommendation + priority

## Tasks
- [ ] Read each prompt's code path, extract current context assembly
- [ ] Add temporary log lines (or use existing logs) to capture real prompt length on a recent call for token-budget measurement
- [ ] Write the audit doc section by section
- [ ] Include a summary table at the top
- [ ] Commit

## Dev Tests
- N/A — this is a documentation deliverable. Reviewer (the user) must read and sign off before Story 10.6 begins.

## Out of Scope
- Any prompt changes (that is Story 10.6)
- Evidence API / UI (Stories 10.3–10.5)
