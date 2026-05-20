# Epic 10 — Prompts Audit

**Date:** 2026-04-21
**Story:** 10.2 — read-only deliverable. Drives Story 10.6 fixes.
**Scope:** Every LLM prompt in the Call Tracker pipeline — what it sees today, what it needs, what to change.

---

## Important finding: 5 prompts, not 6

The design doc (§4.5) assumed 6 prompts: extraction, auto-match, per-topic merge, merge verification, not-discussed verification, and artifacts. In the actual codebase, **there is no auto-match LLM prompt**. Matching between call topics and existing project topics is 100% user-driven via the Project Matching stage UI (M:N drag-and-assign, persisted as `topic_match_groups`). This simplification happened during Epic 9 and is correct — it removes LLM bias from the matching step and puts the user in control. The `"project_topics"` stored prompt is used only inside `run_merge_preview` as the `base_merge_instructions` for per-topic synthesis.

So this audit covers **5 LLM prompts**.

---

## Summary table

| # | Prompt | File:line | Priority | Recommended fix | Expected in Story 10.6 |
|---|---|---|---|---|---|
| 1 | Call Topics Extraction | `topics_service.py:261-316` | **Should** | Pass existing project topic names as a vocabulary hint so new call topics align with prior naming conventions | Yes |
| 2 | Per-topic Merge (CRITICAL RULES) | `topics_service.py:551-712` (inline in `run_merge_preview`) | **Done in 10.1** | Already fixed — now consumes `build_lineage_evidence_block` which walks archived ancestors | Already shipped |
| 3 | Merge Verification | `topics_service.py:681-809` | **Must** | Include ancestor calls' excerpts (via `get_lineage_topic_updates`) so Call-N verification sees commitments from pre-merge Call-1 sources | Yes |
| 4 | Not-Discussed Verification | `topics_service.py:836-926` | **Could** | Optional: include latest 1-2 prior excerpts for the topic so the verifier distinguishes "stale" from "not-discussed-this-call" | Deferred — low value given current scope |
| 5 | Artifacts (project scope) | `routers/artifacts.py:249-255` + `topics_service.py:1853-1874` | **Should** | Replace `get_project_topics_context` with lineage-aware rendering; let project-scope artifacts see per-call evolution, not only current state | Yes |

---

## Prompt 1 — Call Topics Extraction

**Source:** `backend/services/topics_service.py:261-316` (`extract_call_topics`)
**Stored prompt category:** `call_topics` (artifact_types table, falls back to hardcoded default)
**When it fires:** Background job triggered at the Call Topics stage
**LLM default:** `groq` (Llama 3.3 70B); overridable per-project via `projects.default_llm` or per-prompt via `artifact_types.llm`

**Current prompt text (hardcoded default):**
```
You are an expert at analysing business call transcripts. Extract every
distinct topic discussed — be exhaustive, do not merge separate topics into
one.

For each topic:
- name: short label (3–6 words)
- summary: 1–2 sentence recap of what was said
- transcript_excerpt: the verbatim relevant section of the transcript where
  this topic was discussed. Include enough context to understand the discussion
  (typically 2–8 sentences). Copy the exact words from the transcript.
- follow_up_items: concrete next steps or open questions (empty array if none)
- decisions: anything explicitly agreed or decided (empty array if none)
- status: open (unresolved), in_progress (being worked on), resolved
  (closed/agreed)
- owner: Us (our team owns it), Client (client owns it), Both (shared)
- sentiment: positive (good news/progress), neutral (informational), concern
  (risk/problem/blocker)

Return ONLY a JSON array. No markdown, no explanation.
```

**Context assembly (`prompt = ...`):**
- `project_context` (from `projects.context`) prepended if non-empty
- The base instruction above (stored or default)
- `_TOPIC_SCHEMA` — JSON schema for the expected response
- `transcript` — raw transcript of **this call only**

**What the LLM sees today:** `{project_context?, instruction, schema, transcript}`.

**What it does NOT see:**
- Existing project topic names or summaries
- Prior call excerpts
- Prior call topics or decisions

**Call-count dependency:** None. Input is always `project_context + transcript`. Extraction output quality per call is independent of call count — which is actually the explicit design goal ("no previous context — eliminates extraction bias", see `extract_call_topics` docstring).

**Token-budget envelope:** Approx 1,500 chars instruction + 3,000–20,000 chars transcript. Well within any model's context window. No growth with N.

**Blindness identified:**
- **Naming inconsistency across calls.** Without seeing prior project topic names, the LLM will coin a slightly different label for the same concept (e.g. "API strategy" in Call 1 → "API approach" in Call 3). This forces the user to do extra matching work and creates false "new topic" classifications.
- **No awareness of prior decisions.** If Call 1 decided "REST for MVP" and Call 3 discusses "GraphQL migration Q4", the extractor has no reason to flag the contradiction.

**Recommended fix (Story 10.6):**
- Add an OPTIONAL vocabulary hint: pass project topic names only (not full summaries) as a short list under the header "Existing project topic names (align your `name` field to these when the same subject is discussed):".
- Do NOT pass summaries or decisions (deliberately — keeps extraction focused on the current transcript). The hint is vocabulary-only.
- Rationale: preserves the no-bias property (LLM isn't anchored to prior summaries) while nudging naming consistency.

**Deferred:**
- Passing prior decisions for contradiction detection — broader scope, worth its own story if needed.

**Status:** implemented 2026-04-21 — commit 8e68c3e

---

## Prompt 2 — Per-topic Merge (CRITICAL RULES)

**Source:** `backend/services/topics_service.py:551-712` (inside `run_merge_preview.merge_one`)
**Stored prompt category:** `project_topics` (misleadingly named — see header note above)
**When it fires:** Background job when user clicks "Run merge" at Project Updates stage. One LLM call per match group (1:1 or M:N).
**LLM default:** per-project `default_llm`, overridable per-prompt

**Current prompt text (hardcoded default `base_merge_instructions`):**
```
You are merging an existing project topic record with one or more new call
topics that match it. Produce an updated topic that synthesises the history
with the latest call information.

CRITICAL RULES — follow these exactly:
1. NEVER drop follow-up items. Include ALL follow-ups from ALL sources
   (existing + new). If both the existing topic and the call topic have
   follow-ups, UNION them — do not pick a subset.
2. NEVER drop decisions. Include ALL decisions from ALL sources.
3. The summary must cover ALL key points discussed — do not compress or omit
   details. If the discussion touched on specific numbers, dates, names, or
   commitments, include them.
4. When in doubt, include more detail rather than less. Completeness beats
   brevity.
5. Update status, sentiment, and owner to reflect the CURRENT state after this
   call.
6. Preserve the exact wording of follow-up items and decisions unless they are
   truly duplicates.
```

**Context assembly:** Varies by path (new-topics merge / 1:1 / M:N), all three paths consume `build_lineage_evidence_block(name, topic_id, db)` (Story 10.1) which now walks archived ancestors. Each path also includes the current call's pending topic data with follow-ups and decisions bulleted per call.

**What the LLM sees today (post-Story-10.1):**
- Merge instructions (hardcoded or stored)
- Ancestor-aware per-call evidence: for each contributing call, `Transcript: …`, `Summary: …`, `Follow-ups from this call: …`, `Decisions from this call: …`
- Provenance line `(from archived topic: {name})` when a row originated from an archived M:N source
- Current call's pending topic data inline
- `_TOPIC_SCHEMA` for response

**Call-count dependency:** LINEAR growth with call count via the evidence block. At Call N, the evidence block contains up to N-1 prior cards per topic.

**Token-budget envelope:**
- Per-call evidence card: ~300–1,200 chars depending on excerpt length
- At Call 10 with 8 prior calls touching a single topic: ~10kB block per topic → well under Claude/GPT limits (200k tokens)
- At Call 50: ~60kB block → still fits but getting large. Revisit compression if users hit this.

**Blindness identified:** None critical after Story 10.1. The lineage walker now includes archived ancestors.

**Recommended fix:** None for Story 10.6. Confirm in audit doc that Story 10.1 closed the blindness. Track token-budget observation as Call count scales.

**Status:** already shipped in Story 10.1 (commit dbabdb1)

---

## Prompt 3 — Merge Verification

**Source:** `backend/services/topics_service.py:681-809` (`_verify_merged_topics`)
**Stored prompt category:** `merge_verification` (seeded by `DEFAULT_MERGE_VERIFICATION_PROMPT`)
**When it fires:** Right after per-topic merge, inside `run_merge_background`. One LLM call per discussed merged topic.
**LLM default:** per-project

**Current prompt text (hardcoded default):**
```
You are a quality reviewer for project topic data. Verify that the merged
topic did NOT lose any important information. Check: are ALL follow-up items
preserved? ALL decisions? Does the summary cover all key points? Return the
corrected topic as JSON. Only ADD back what was lost, never remove anything.
```

**Context assembly (per topic):**
```
{verify_instructions}

== Merged topic (to verify) ==
{json.dumps(merged_topic)}

== Source follow-up items (must ALL be present) ==
{all_follow_ups_from_every_source}

== Source decisions (must ALL be present) ==
{all_decisions_from_every_source}

== Relevant section of call transcript ==
{transcript[:8000]}        ← ONLY CURRENT CALL's transcript, truncated to 8k chars

Return the corrected topic JSON (same schema). ...
```

**What the LLM sees today:**
- Current merged topic JSON
- Flattened list of all source follow-ups + decisions from both archived project topics and current call pending topics
- **Only the current call's transcript** (truncated to 8k chars)

**What it does NOT see:**
- **Ancestor calls' transcripts or excerpts.** For a Call-10 merge that fans in an M:N ancestor from Call 3, the verifier does not see Call 3's transcript. It can't cross-check "did we preserve Call 3's commitment?" against evidence — only against the flat follow-up list.
- **Prior-call excerpts.** Even cheaper than full transcripts, these would give the verifier grounded evidence of what was said.

**Call-count dependency:** Flat. The verifier always sees only the current call's transcript regardless of how many prior calls contributed evidence.

**Token-budget envelope:** `8,000 + source_lists (~1-3kB) + merged_topic (~500 bytes)` ≈ 10kB. Tiny.

**Blindness identified (CRITICAL):**
- **Ancestor-call evidence invisible.** If a Call-5 merge on a topic that was M:N-merged in Call 2 drops a commitment that was originally made in Call 1, the verifier has no way to detect it — Call 1's transcript isn't in the prompt, and the flat `all_follow_ups` list can't tell the verifier where each item came from or whether the merged topic's summary still covers it.
- **Transcript truncation.** The `transcript[:8000]` truncation silently throws away the last part of long transcripts. If the commitment in question was in the last 20% of the call, the verifier can't see it.

**Recommended fix (Story 10.6, MUST):**
- Replace the current `source_follow_ups` / `source_decisions` context with a full ancestor-aware evidence block built from `get_lineage_topic_updates(topic_id, db)`. The block format matches Story 10.1's `build_lineage_evidence_block` so the verifier sees per-call transcript excerpts with provenance.
- Keep the current-call transcript field but rename to make it clear (`== Current call transcript ==`) and remove the `[:8000]` truncation (or raise to 20k).
- Update the instruction text: "verify ALL key points from ALL calls in the lineage are preserved, not just the current call's."

**Deferred:** Multi-model consensus verification (running two LLMs and comparing) — out of scope.

**Status:** implemented 2026-04-21 — commit fd45fc4

---

## Prompt 4 — Not-Discussed Verification

**Source:** `backend/services/topics_service.py:836-926` (`verify_not_discussed_topics`)
**Stored prompt category:** `not_discussed_check`
**When it fires:** Background job triggered at Project Matching stage save. One LLM call per not-discussed project topic.
**LLM default:** per-project

**Current prompt text (hardcoded default):**
```
You are checking whether a project topic was actually discussed in a call
transcript.
Given the topic name, its latest summary, and the full call transcript,
determine:
1. Was this topic mentioned or discussed in the call? (yes/no)
2. If yes, provide the relevant transcript excerpt.

Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null,
"reasoning": "one sentence explanation"}
```

**Context assembly (per topic):**
```
{check_instructions}

Topic name: {topic.name}
Topic summary: {topic.summary}

Call transcript:
{full transcript}          ← NOT truncated
```

**What the LLM sees today:**
- Topic name + latest summary (post-latest-merge state)
- **Full** current call transcript
- That's it.

**Call-count dependency:** Flat. Always exactly the current call's transcript. Topic summary grows in richness as the topic accumulates history, but the summary is already the latest-merge state.

**Token-budget envelope:** `~500 bytes instruction + 200 bytes topic + full transcript (5-30k)` ≈ 6-30kB. Fits.

**Blindness identified (MINOR):**
- **No prior-call context.** The verifier judges "was this topic discussed THIS call?" without any reference to how the topic last appeared. Normally fine, but edge cases (e.g., the topic was resolved 2 calls ago and is trivially referenced this call as "we already closed that") would benefit from prior context.
- **Name-only matching.** The topic summary is a post-merge synthesis — it may use different vocabulary than the transcript. The verifier has to bridge this gap each call.

**Recommended fix (Story 10.6, COULD — deferred):**
- Low priority. Current prompt works well in practice. The main risk is false negatives (verifier says "not discussed" when the topic was briefly mentioned), and those are already handled by the user-facing "Promote to Updated" flow (see ERR-004 fix).
- If we do tackle it: inject the most recent 1-2 prior `transcript_excerpt` values for the topic as "Prior discussion examples". Keeps prompt short, gives the verifier grounded vocabulary.

**Decision:** Defer unless false-negative rate becomes a concern.

**Status:** deferred — low priority per audit; revisit if false-negative rate becomes a concern

---

## Prompt 5 — Artifacts

**Source:** `backend/services/llm_service.py:86` (`generate_artifact`) invoked from `backend/routers/artifacts.py:255`
**Stored prompt category:** `artifacts` (user creates these per artifact type — no single hardcoded prompt)
**When it fires:** User-triggered at Artifacts stage. One LLM call per selected artifact.
**LLM default:** per-artifact-type, falls back to per-project

**Prompt text:** User-defined per artifact type (Executive Summary, Next Steps, Email Summary, etc.). See `DEFAULT_ARTIFACT_TYPES` in `routers/artifact_types.py`.

**Context assembly (`routers/artifacts.py:247-255`):**
```python
full_context = transcript
if scope == "project" and project_topics_context:
    full_context = f"{transcript}\n\n{project_topics_context}"
effective_prompt = (
    f"Project context:\n{project_context}\n\n{prompt_used}"
    if project_context else prompt_used
)
content = await generate_artifact(effective_prompt, full_context, mode, topics=call_topics)
```

**`project_topics_context` is built by `get_project_topics_context(project_id)`** at `topics_service.py:1853-1874`:
- Iterates all non-archived project topics with `status` in (`open`, `in_progress`)
- Emits `• {name} [{status}/{owner}/{sentiment}]\n  Latest: {summary}\n  → {first 3 follow-ups}`
- **No per-call history, no decisions, no archived-ancestor evidence**

**What the LLM sees today:**
- `project_context` (string on `projects.context`)
- User's artifact-type prompt
- Full transcript of current call
- For `context_scope="project"`: a flat snapshot of all open/in-progress topics with summary + top-3 follow-ups

**What it does NOT see (project scope only):**
- Per-call evolution of any topic — just the current state
- Decisions (the context builder deliberately skips decisions)
- Resolved topics (skipped — only open/in-progress shown)
- Archived-ancestor history (the snapshot reads `previous` via `_get_previous_topics`, which filters out archived)

**Call-count dependency (project scope):** Flat. The snapshot always reflects the current state, regardless of how many calls contributed.

**Token-budget envelope:** Current transcript (5-30k) + `project_topics_context` (~2-5k at scale) = small. Fits.

**Blindness identified:**
- **Project-scope artifacts can't narrate evolution.** An Executive Summary for a 3-call project that says "API approach was decided in Call 1 and confirmed in Call 3 after spiking GraphQL in Call 2" requires per-call decision history. Current `get_project_topics_context` can't produce this.
- **Decisions invisible.** The current context builder skips `decisions` entirely — surprising for an artifact generator whose job is to report decisions.
- **Archived history invisible.** An "API strategy" topic that was M:N-merged from "REST" + "GraphQL" in Call 2 loses the fact that two competing approaches were once considered.

**Recommended fix (Story 10.6, SHOULD):**
- For `context_scope="project"`, replace the flat `project_topics_context` with a richer lineage-aware rendering:
  - For each open/in-progress topic, emit `build_lineage_evidence_block(name, topic_id, db)` (the Story 10.1 helper) instead of the current single-line summary
  - Includes decisions per call, follow-ups per call, transcript excerpts, ancestor provenance
- Add a new helper `get_project_topics_lineage_context(project_id)` that returns the combined block (instead of modifying `get_project_topics_context` to avoid breaking call-scope behavior).
- Token budget: at Call 10 with 20 active topics, each with ~5kB evidence block = 100kB. At Call 20 ≈ 200kB. Claude Opus/Sonnet handles this; GPT-4o handles it; smaller models may struggle. Cap at most-recent-3-calls per topic if budget becomes a concern (defer the cap).

**Deferred:**
- Citation tracking (click a sentence → jump to source topic) — not scoped to Epic 10 per user decision.

**Status:** implemented 2026-04-21 — commit ecce0ed

---

## Story 10.6 scope summary

Based on this audit, Story 10.6 should:

1. **(SHOULD)** Pass existing project topic names as vocabulary hint to **Call Topics Extraction** (Prompt 1)
2. **(DONE via 10.1)** Confirm **Per-topic Merge** (Prompt 2) is already using `build_lineage_evidence_block` — no action
3. **(MUST)** Rewrite **Merge Verification** (Prompt 3) to use `get_lineage_topic_updates` for ancestor-aware evidence; remove the `transcript[:8000]` truncation
4. **(COULD, deferred)** Add prior-call context to **Not-Discussed Verification** (Prompt 4) — not this story
5. **(SHOULD)** Replace flat `get_project_topics_context` with lineage-aware `get_project_topics_lineage_context` for project-scope **Artifacts** (Prompt 5)

Each fix gets:
- One failing test demonstrating the blindness (TDD)
- Minimal implementation
- Token-budget re-measurement after the fix
- A dedicated `[EPIC-10]` commit

---

## Token budget tracking

Record the actual prompt length for each LLM call in the backend logs so we can track growth per project. Current logging is absent — consider adding `logger.info(f"[LLM] Prompt length: {len(prompt)} chars for …")` at each `_call_llm` site. Out of scope for Story 10.2 but noted here for future visibility.
