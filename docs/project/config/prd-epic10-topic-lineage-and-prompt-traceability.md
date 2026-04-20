# PRD — Epic 10: Topic Lineage + Prompt Traceability

**Status:** Locked
**Date:** 2026-04-20
**Author:** Louis Garnier
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md`

---

## Problem

After Epic 9 shipped M:N merges and not-discussed verification, real-world testing revealed that information decay accelerates with every call:

1. When topics are M:N merged, the new merged topic starts with a clean slate — the archived source topics' `topic_updates` (including transcript excerpts from earlier calls) are unreachable to the merged topic's future merges. A merge at Call 10 touching a topic first raised in Call 1 and merged in Call 3 is effectively blind to Call 1's evidence.
2. The user cannot see what the LLM used to produce a merge. Transcript excerpts, per-call summaries, follow-ups, decisions, and match decisions are all persisted but never surfaced in the frontend. Validating merge quality requires reading the database directly.
3. Merge-result topics look identical to fresh topics in the Topics Timeline — the visual distinction between "raised for the first time in this call" vs "created by combining existing topics" is lost.
4. The six LLM prompts in the pipeline each assemble their own context ad-hoc. No one has audited what each prompt actually sees, what it should see, or how its context scales with call count. As the project moves from 1 to 10+ calls, prompts that once worked fine degrade silently.

The user's explicit ask: **always preserve the history of topics, and at every stage of the Kanban (call topics, project matching, project updates), always have access to the excerpts, the summaries of those extracts, the match decisions, and the full data needed for the specific topic or merged topic — so that every prompt can see it all.**

---

## Goals

1. **Lineage integrity**: every merge prompt, at every call, sees every ancestor topic's transcript excerpt and per-call history. M:N merges stop causing data loss.
2. **Visible traceability**: a per-topic evidence panel exposes the complete per-call trail (transcript excerpt, merged summary, follow-ups, decisions, match group, raw pre-merge extract), color-coded by call.
3. **Merge provenance**: the Topics Timeline visually distinguishes merge-result topics from fresh topics.
4. **Prompt audit coverage**: every LLM prompt in the pipeline is documented: what it sees today, what it needs, what the fix is. Each fix is either implemented or explicitly deferred.
5. **Single source of truth**: one backend lineage helper powers both prompt context assembly and the frontend evidence display — no duplicated logic, no drift.

---

## Non-Goals

- No new database columns or migrations. Epic 10 is a read-layer and prompt-layer improvement on top of Epic 9's schema.
- No changes to how topics are extracted, matched, or merged at the logic level — only to the context each prompt receives.
- No per-item follow-up lifecycle (open/resolved/superseded tracking). UNION semantics retained.
- No token-budget compression strategies for very long lineages. Measured first; implemented only if we hit real limits.
- No backfill of `transcript_excerpt` on pre-migration `topic_updates`. Heals as new calls come in.
- No un-merge soft-delete. Current hard-delete on rollback retained.
- No manual cross-call topic merge UI. M:N merges happen only during the active call's project matching stage.

---

## User Stories

**US-10.1 — Merge quality survives M:N**
As a user running a merge on Call N for a topic that was M:N-merged in Call M (M<N), I want the merge prompt to still see every source topic's transcript excerpts from calls before M, so the merge doesn't quietly lose information that existed before the merge happened.

**US-10.2 — See what the prompt saw**
As a user reviewing an updated topic on the Project Updates stage, I want to expand a panel and see, per call in chronological order, the transcript excerpt, the summary after that call, the follow-ups, and the decisions — so I can verify the LLM didn't drop anything.

**US-10.3 — See the full lineage on the timeline**
As a user browsing the Topics Timeline, I want to click any cell and see the full per-call evidence trail for that topic, including evidence from ancestor topics if the topic was the result of a merge — so I understand the complete history at a glance.

**US-10.4 — Tell merged-in topics apart from fresh ones**
As a user scanning the Topics Timeline, I want merge-result topics to be visually distinct from genuinely fresh topics (different color, different label), and to be able to hover to see which source topics it came from — so I'm not confused about what's new vs what's a reorganization.

**US-10.5 — Know what each prompt sees**
As a developer maintaining this pipeline, I want a single audit document that lists every LLM prompt, its current context assembly, its blindnesses, and the recommended fix — so future changes are informed and prompt quality is a first-class concern.

**US-10.6 — Prompts scale with call count**
As a user approaching 10+ calls on a project, I want every prompt (extraction, match, merge, verification, artifacts) to have the historical context it needs to produce high-quality output at Call 10, not just Call 1.

**US-10.7 — Understand why a topic was extracted**
As a user viewing the Call Topics stage, I want to click any extracted topic and see the verbatim transcript excerpt that caused the LLM to extract it, plus the summary/follow-ups/decisions it generated — so I can confirm the extraction grounded in real content.

**US-10.8 — Understand the reasoning behind every match decision**
As a user reviewing the Project Matching stage, I want to click any match decision (followed-up / new / not-discussed) and see side-by-side: the existing project topic's full historical evidence (every prior call's excerpt + summary) on the left, and the current call's extraction on the right — so I can read both sides and understand the classification without needing persisted LLM reasoning. This gives me a clear historical trace of how we got to this state for any topic.

---

## Functional Requirements

### FR-10.1 Lineage helper
A backend module `topic_lineage.py` exposes:
- `get_topic_lineage(topic_id)` — returns every ancestor topic reachable by walking `merged_into_topic_id` backwards.
- `get_lineage_topic_updates(topic_id)` — returns all `topic_updates` rows for a topic and its ancestors, enriched with `source_topic_id` and `source_topic_name`, ordered by `created_at`.
- `get_lineage_match_groups(topic_id)` — returns `topic_match_groups` rows whose `project_topic_ids` contains this topic or any ancestor.

The existing `_load_transcript_excerpts` helper in `topics_service.py` is replaced by a call to `get_lineage_topic_updates` so every merge prompt automatically gains ancestor visibility.

### FR-10.2 Evidence API
`GET /api/topics/{topic_id}/evidence` returns an ancestor-aware chronological per-call array containing, for each call that touched the topic or any ancestor: transcript_excerpt, merged_summary, follow_up_items, decisions, status, raw_extract (from `pending_topics`), match_group (from `topic_match_groups`), not_discussed_verification (from `calls.verification_cache`), source_topic_id/name, and call metadata (title, date).

### FR-10.3 Evidence drawer UI (full-overlay, multi-stage)
A reusable React component `TopicEvidenceDrawer` opens as a full-overlay modal-style drawer (approved via mockup 2026-04-20). Supports three modes:

**`mode="lineage"`** — full ancestor-aware per-call trail. Content: lineage chip at top for merge-result topics + one color-coded card per call (chronological). Each card expands to show transcript excerpt (verbatim), merged summary, follow-ups, decisions, and (collapsed by default) raw pre-merge extract, match group, not-discussed verification details.

**`mode="call_topic"`** — single-panel view of a pending call topic's raw extraction data (transcript_excerpt + summary + follow-ups + decisions + status/owner/sentiment). No network call; uses existing pending_topics data.

**`mode="matching"`** — two-column side-by-side layout. Left column reuses `mode="lineage"` for the existing topic. Right column shows the current call's pending_topic data. Footer strip explains the classification based on the visible data (not persisted LLM reasoning).

The drawer is mounted on every Kanban stage where evidence aids user understanding:
- **Call Topics stage** → `mode="call_topic"`
- **Project Matching stage** → `mode="matching"`
- **Project Updates stage** → `mode="lineage"` (richest view — validates that the merge preserved everything)
- **Topics Timeline** → `mode="lineage"`

Close via X button, Esc key, or click outside.

### FR-10.4 Merge-result labeling
Timeline cells on merge-result topics render as `+ new (merged)` in a distinct color (purple), with a tooltip listing source topic names. Detection: `topics WHERE merged_into_topic_id = this_topic.id` returns rows ⇒ `has_sources = true`.

### FR-10.5 Prompts audit document
`docs/project/config/epic-10-prompts-audit.md` exists, covers all six prompts (Call Topics Extraction, Project Topics Merge, Per-topic Merge, Merge Verification, Not-Discussed Verification, Artifacts), and provides for each: current inputs (with file/line reference), call-count dependency, identified blindnesses, recommended fix, token-budget observation, and post-fix status (implemented / deferred + reason).

### FR-10.6 Prompt fixes
Each recommended fix from the audit is implemented in a discrete commit in Story 10.6 unless deferred with explicit rationale recorded in the audit doc. Expected fixes (subject to audit):
- Extraction prompt receives existing project topic vocabulary
- Match prompt receives historical transcript excerpts (not just summaries)
- Merge verification prompt receives ancestor-call transcripts via lineage helper
- Not-discussed verification prompt receives prior-call excerpts for the topic
- Artifacts project-scope prompt receives full `topic_updates` history via lineage helper

---

## Acceptance Criteria

- [ ] A Call-10 merge on a topic first raised in Call 1 and M:N-merged in Call 3 produces a prompt whose text contains Call 1's transcript_excerpt. (Test: `tests/test_topic_lineage.py::test_ancestor_excerpt_in_merge_prompt`.)
- [ ] Clicking a Topics Timeline cell opens the evidence drawer in `mode="lineage"`; the drawer shows one card per call that touched the topic or any ancestor.
- [ ] The evidence drawer for an M:N-merge-result topic shows a lineage chip listing both source topic names.
- [ ] A Timeline cell for a merge-result topic visually differs from a fresh topic cell; hover reveals source topic names.
- [ ] On the Call Topics stage, clicking any extracted topic opens the drawer in `mode="call_topic"` with its transcript excerpt + summary + follow-ups + decisions visible.
- [ ] On the Project Matching stage, clicking "Show evidence" on any row opens the drawer in `mode="matching"` with correct left/right content per classification kind and the footer strip explanation.
- [ ] `epic-10-prompts-audit.md` exists, committed, references every prompt by file and line, and has a completed "recommendation" column for each row.
- [ ] Every recommendation in the audit is marked "implemented" (with commit reference) or "deferred" (with rationale) by the end of Story 10.6.
- [ ] All Epic 9 tests still pass. No regression on existing 1:1 merges, single-call extraction, or Timeline rendering.

---

## Dependencies

- Epic 9 complete (M:N schema, transcript_excerpt, verification cache).
- Epic 7 complete (`pending_topics` retention).

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Lineage walker produces infinite loop on cyclic merges | Visited-set guard + assertion; M:N merge creation code already forbids cycles by construction |
| Token budget blown by long lineages | Measured in Phase 2 audit; compression strategies deferred until measured need |
| Evidence panel overwhelming for topics with 20+ calls | Collapsed-by-default cards, chronological ordering, visual cues for most recent |
| Prompt audit changes recommended fixes mid-Story-10.6 | Each fix is a discrete commit; audit doc is source of truth; deferring is a valid outcome |

---

## Success Metrics (qualitative)

- User can answer "what transcript grounded this merge?" in under 3 clicks for any topic.
- Zero reports of "merge dropped information from an earlier call" after Story 10.1 ships.
- Developer-facing: the prompts audit is the reference consulted before modifying any prompt.
