# Call Topics Extraction Overhaul — Design

**Date:** 2026-04-22
**Status:** Draft — pending user review
**Relates to:** [Epic 10 Prompts Audit](./epic-10-prompts-audit.md) (Prompt 1), [CallTopicsStage.tsx](../../../frontend/src/components/CallTopicsStage.tsx), [topics_service.py:261-341](../../../backend/services/topics_service.py)

---

## 1. Problem

Call topic extraction today produces output the user doesn't trust:

- **Fragmentation.** The prompt says *"extract every distinct topic — do not merge separate topics into one"*, causing near-duplicates ("REST vs GraphQL debate", "API contract timeline", "mobile team impact" — all one thread).
- **Thin summaries.** Prompt caps summaries at "1–2 sentences", losing the numbers, names, commitments that make a topic actionable.
- **Opaque importance.** Nothing signals why a topic was picked — is it a real decision point or just noise?
- **Conflated anchors.** `decisions[]` and `follow_up_items[]` are the only structured fields; actions, open questions, and commitments all collapse into `follow_up_items[]` with no distinction.
- **Tile surfaces too little to trust.** Current `TopicRow` shows name + 1-line summary + arrow follow-ups. Decisions are invisible until you expand the edit view. No excerpt preview. No importance cue.

User quote: *"Topics are really the key to all this process. If we extract correct topics, then the whole flow will be smoother."*

## 2. Goals

- **Fewer, bigger, more trustworthy topics** per call — 3-of-4 criteria rubric, no near-duplicates.
- **Rich tiles** — user can judge topic quality, read decisions/actions/open-questions inline, without opening a drawer.
- **Structured anchor types** — decisions, actions, open questions as three distinct first-class fields.
- **Parked items** — a way to capture "flagged for later, no current action."

## 3. Non-goals

- **No changes to the matching or merge stages** (Project Matching / Project Updates). Those already work. Scope is the Call Topics stage only.
- **No artifact-context feedback loop.** Artifacts consume topics; they do not feed extraction. Rationale: if topics are correct, artifacts are correct by consequence. Data flows one way.
- **No new "project pillars" taxonomy** field on projects. Existing `projects.context` stays as-is; new prompt references it.
- **No continuous importance score.** Extractor emits an `importance` enum (`high | medium | low`) tied directly to rubric-criteria count (§4.3). No floating-point scores like `0.87` — three discrete buckets matching the red/amber/grey dot only.
- **No action-item objects with owners/due dates.** Actions stay as strings for this pass (Option B schema, not C). Owners embedded in prose via `"Nick: run benchmark"` convention. Upgrading to object shape is a later story if needed.
- **No removal of direct provider SDKs.** OpenRouter is added as a *4th* provider alongside `groq`, `claude`, `openai` — not a replacement. Existing projects / artifact types keep working. Users opt into OpenRouter per artifact type.

## 4. Design

### 4.1 The rubric (prompt heart)

A candidate is a topic when it meets **at least 3 of 4** criteria:

1. **Forward life** — needs attention after this call (not resolved the moment it was uttered).
2. **Anchor type** — has at least one of: a *decision pending*, an *action outstanding*, or an *open question / uncertainty*.
3. **Specificity** — references named systems, metrics, people, frequencies, or timelines.
4. **Dialogue depth** — ≥2 substantive turns (raised + responded to with information, pushback, question, or commitment).

**Splits:** break into separate topics when sub-items have different owners, different timelines, or could be decided independently. Keep together when sub-items are inputs to one decision.

**Filters:** drop re-explanations / onboarding narration (test: *"did anything new get decided or raised?"*). Drop pure logistics resolved in-call (meeting reschedules, CC lists). Parked items (future life, no current action) → extract but set `is_parked = true`.

### 4.2 New extraction prompt structure

Single LLM call. Prompt is built in six named blocks in this order:

```
[ROLE]       You are an expert analyst of business call transcripts.
             Your output shapes a living project tracker. Precision and
             discipline matter more than coverage.

[RUBRIC]     <the 4 criteria + split/merge rules + filter rules above>

[ANCHORS]    Exactly three anchor types:
             - Decisions: anything explicitly agreed or concluded
             - Actions:   concrete next steps with implicit or explicit owner
             - Open questions: unresolved uncertainties needing investigation

[FEW-SHOT]   One good extraction (consolidated, well-anchored) with a
             one-line rationale per topic. One bad extraction (fragmented,
             near-duplicates, filler) with inline corrections. ~400 tokens.

[PROCESS]    Chain-of-thought instruction:
             Step 1 — list every candidate thread
             Step 2 — cluster near-duplicates by shared subject + shared
                      commitments
             Step 3 — apply 3-of-4 criteria; drop failures
             Step 4 — for each surviving cluster, synthesize summary with
                      every concrete detail (numbers, names, frequencies,
                      deadlines); classify anchors into decisions /
                      actions / open_questions
             Step 5 — flag is_parked when future-life but no current action

[CONTEXT]    - Project context: {projects.context}
             - Existing project topic names (vocabulary alignment —
               do NOT invent new names for existing subjects):
               {names list}
             - Transcript:
               {full transcript}
```

**Stored prompt precedence:** same as today — if `artifact_types.prompt` for `call_topics` category is set, it replaces the default `[ROLE] + [RUBRIC] + [ANCHORS] + [FEW-SHOT] + [PROCESS]` block. `[CONTEXT]` is always appended by the system. Users overriding the prompt accept responsibility for the rubric — document this in the UI helper text.

### 4.3 Output schema (Option B)

```json
{
  "name": "3–6 words",
  "summary": "3–6 sentences covering every concrete detail — numbers, names, frequencies, deadlines",
  "transcript_excerpt": "verbatim relevant section, 2–8 sentences",
  "decisions":      ["string", "..."],
  "follow_up_items": ["Nick: run benchmark", "..."],   // actions — owners inlined as prefix
  "open_questions":  ["Does X apply when Y?", "..."],  // NEW
  "status":    "open | in_progress | resolved",
  "owner":     "Us | Client | Both",
  "sentiment": "positive | neutral | concern",
  "is_parked":  false,                                   // NEW
  "importance": "high | medium | low",                   // NEW — drives the tile's importance dot
  "rationale":  "One sentence — which rubric criteria were met."   // NEW — tooltip on the dot
}
```

**New fields:**
- `open_questions: string[]` — default `[]`
- `is_parked: boolean` — default `false`
- `importance: "high" | "medium" | "low"` — default `"medium"`. Prompt instructs: `high` = all 4 rubric criteria met; `medium` = 3 of 4; `low` = parked or weak-specificity edge cases. Drives the importance-dot colour on the tile (red / amber / grey).
- `rationale: string` — default `""`. Rendered as a hover tooltip on the importance dot — not as footer text. Explains *why* this importance level.

**Removed fields:** none.

**Renamed fields:** none. `follow_up_items` keeps its name (avoid cascading TS/Python type renames) but prompt re-scopes its meaning to actions-only. Decisions go in `decisions[]`, questions in `open_questions[]`.

### 4.4 Model choice — OpenRouter integration

The quality bar the new prompt aims for (3-of-4 rubric, consolidation, chain-of-thought, structured JSON) is model-sensitive. Current default `groq` (Llama 3.3 70B) struggles with multi-step reasoning of this shape. Rather than hard-coding a better model per provider, add **OpenRouter as a 4th provider** — unified API, one key, catalog of all credible models — and curate a per-category recommended list in the UI.

#### 4.4.1 Provider model

```
llm ∈ {'groq', 'claude', 'openai', 'openrouter'}
```

- `groq` / `claude` / `openai` — direct SDKs, keep current behavior. Model is implicit per provider.
- **`openrouter` (new)** — dispatches via OpenRouter's OpenAI-compatible API. Requires a **model slug** (e.g. `anthropic/claude-sonnet-4.6`).

#### 4.4.2 New field: `artifact_types.model`

```sql
ALTER TABLE artifact_types ADD COLUMN model TEXT;
```

- Nullable string. Only consulted when `llm = 'openrouter'`.
- When `llm != 'openrouter'`, the column is ignored (keep set to NULL for clarity).
- No validation beyond "non-empty when `llm='openrouter'`" — trust the OpenRouter API to reject unknown slugs. Surface its error back to the user.

#### 4.4.3 Dispatch in `llm_service.py`

Add a fourth branch:

```python
elif llm == "openrouter":
    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    response = await client.chat.completions.create(
        model=model,                      # required — caller passes it through
        messages=[{"role": "user", "content": prompt}],
        ...
    )
```

Same 3-retry exponential-backoff envelope as the other providers. Optional `HTTP-Referer` / `X-Title` headers for OpenRouter dashboard attribution — set to `"Call Tracker"` / project URL.

Signature change: `generate_artifact(prompt_used, transcript, llm, topics=None, *, model: str | None = None)`. Call sites in `artifacts.py` and `topics_service.py` read `model` from the artifact type row when resolving the effective config.

#### 4.4.4 Curated recommendations (frontend UI affordance, not enforced in backend)

Per-category recommended slugs shown in the model dropdown. Backend doesn't validate against this list — it's UI sugar.

| Category | Best (default) | Strong alt | Balanced | Budget | Fallback |
|---|---|---|---|---|---|
| `call_topics` | `anthropic/claude-sonnet-4.6` | `openai/gpt-4o` | `google/gemini-2.5-pro` | `deepseek/deepseek-chat` | `meta-llama/llama-3.3-70b-instruct` |
| `artifacts`   | `anthropic/claude-sonnet-4.6` | `openai/gpt-4o` | `google/gemini-2.5-pro` | `deepseek/deepseek-chat` | `meta-llama/llama-3.3-70b-instruct` |
| `merge_verification` | `anthropic/claude-sonnet-4.6` | `openai/gpt-4o` | `google/gemini-2.5-pro` | — | — |
| `not_discussed_check` | `google/gemini-2.5-pro` | `openai/gpt-4o-mini` | `deepseek/deepseek-chat` | — | — |

Curated list lives in a frontend constant `MODEL_RECOMMENDATIONS: Record<ArtifactCategory, Array<{slug, tier, label}>>`. Users can also type a custom slug — "Custom…" row at the bottom of the dropdown.

#### 4.4.5 Defaults

- **New projects**: seed `call_topics` artifact type with `llm = 'openrouter'`, `model = 'anthropic/claude-sonnet-4.6'`.
- **Existing projects**: no migration — they keep whatever `llm` their artifact types have (likely `null` → inherits `projects.default_llm`). Users opt in by editing the artifact type.
- **Project-level `default_llm`**: stays as-is (`'groq' | 'claude' | 'openai' | 'openrouter'`). When set to `'openrouter'`, project also needs `default_model` — add second column `projects.default_model TEXT`. Treat same validation: non-empty iff `default_llm='openrouter'`.

#### 4.4.6 Env var

Add `OPENROUTER_API_KEY` to `backend/.env.example` and document in `README.md`. No new dependency — the `openai` Python package already handles OpenRouter's compatible API.

#### 4.4.7 Cost visibility (nice-to-have, deferred)

OpenRouter returns `usage.prompt_tokens` / `usage.completion_tokens` per call. Surface per-extraction cost estimate in logs — out of scope for this story, tracked as a follow-up.

### 4.5 UI — `CallTopicsStage` tile rewrite

**Current state** ([CallTopicsStage.tsx:43-230](../../../frontend/src/components/CallTopicsStage.tsx#L43-L230)): `TopicRow` has a collapsed view (name + summary + arrows) and an expanded-edit view (dropdowns + editable summary + editable follow-ups). No decisions shown until you expand. No open-questions field. No parked state.

**New tile layout** (Option C — expanded-inline is the default view, not an opt-in):

```
┌────────────────────────────────────────────────────────────────────┐
│ [•] Topic Name                        [STATUS]  SENTIMENT·OWNER  ▾ │
│                                                                    │
│ Rich 3–6 sentence summary with specifics…                         │
│                                                                    │
│ ┌ DECISIONS (1) ────────────────────────────────────────────────┐ │
│ │ ✓ Phase 2 kickoff gated on benchmark outcome.                 │ │
│ └───────────────────────────────────────────────────────────────┘ │
│ ┌ ACTIONS (2) ──────────────────────────────────────────────────┐ │
│ │ → Nick: run benchmark                                         │ │
│ │ → Hassan: share EDS+ evidence                                 │ │
│ └───────────────────────────────────────────────────────────────┘ │
│ ┌ OPEN QUESTIONS (2) ───────────────────────────────────────────┐ │
│ │ ? Does MC Mac's 40GB ceiling apply with caching?              │ │
│ │ ? Can FV Mac handle private markets separately?               │ │
│ └───────────────────────────────────────────────────────────────┘ │
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│ 📄 Source excerpt ↗   ✎ Edit     3 anchors · high specificity     │
└────────────────────────────────────────────────────────────────────┘
```

**Section styling:**
- Decisions — grey background `#f4f5f7`, grey uppercase label
- Actions — amber background `#fff8e6`, `#974f0c` label; owner in `<strong>` when prefix-colon pattern matches (`/^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):/`)
- Open questions — blue background `#eef5ff`, `#0052cc` label
- Empty sections hidden (don't render empty Decisions block)

**Importance dot:** 8px circle, left of topic name. Colour driven by the `importance` field (see §4.3):
- Red `#ae2a19` — `importance: "high"` (all 4 rubric criteria met)
- Amber `#ff991f` — `importance: "medium"` (3 of 4)
- Grey `#97a0af` — `importance: "low"` (parked or weak edge case)

**Hover tooltip on the dot** shows the `rationale` string verbatim (e.g. *"4 of 4 criteria met — named systems, owners, open question, 3 substantive turns"*). No footer text — the rationale does not take permanent tile real estate.

**Parked variant:**
- Border-left grey `#97a0af` instead of blue
- Background `#fafbfc`, opacity `.92`
- `⏸ PARKED` chip in the status slot (replaces normal status badge)
- No Actions section rendered
- Footer "Un-park" button (sets `is_parked = false`)

**Edit mode:**
- Chevron `▾` in header toggles edit affordances — textareas replace render views for each section, add/remove rows, status/owner/sentiment dropdowns appear.
- Summary textarea grows to 5 rows (was 2) to match the 3–6 sentence target.

**Keeps:** `onViewSource` / source excerpt drawer via `TopicEvidenceDrawer mode="call_topic"` — unchanged.

### 4.6 Prompt deployment & lifecycle

The new multi-section prompt is the **one and only** `call_topics` prompt. No parallel hardcoded fallback that diverges from what the UI shows — what you see in the Artifacts tab is what the LLM receives.

#### 4.6.1 What's stored vs system-injected

- **Stored in `artifact_types.prompt` (editable per-project, visible in UI):**
  The full `[ROLE] + [RUBRIC] + [ANCHORS] + [FEW-SHOT] + [PROCESS]` block from §4.2. ~1500 chars. Stable across calls.
- **System-injected at runtime (not editable, not part of the stored prompt):**
  - `projects.context`
  - Existing project topic names (vocabulary hint)
  - `_TOPIC_SCHEMA` (structural contract)
  - The transcript

  Appended after the stored prompt at call time.

#### 4.6.2 Single source of truth

A new Python module `backend/prompts/call_topics.py` exports:

```python
CALL_TOPICS_DEFAULT_PROMPT: str = """[ROLE] …
[RUBRIC] …
[ANCHORS] …
[FEW-SHOT] …
[PROCESS] …"""
```

Consumed in three places, all referencing the same constant:

1. **Seed** — `DEFAULT_ARTIFACT_TYPES["call_topics"].prompt = CALL_TOPICS_DEFAULT_PROMPT` in `routers/artifact_types.py`. Every new project is seeded with this verbatim.
2. **Fallback** — `extract_call_topics` uses `stored_prompt or CALL_TOPICS_DEFAULT_PROMPT`. Identical to the seed. No divergence possible.
3. **"Reset to default" endpoint** — `GET /api/artifact-types/defaults/{category}` returns the current constant so the UI can show/apply it.

#### 4.6.3 Migration for existing projects

One-time migration at release:

```
For each project's `call_topics` artifact type row:
  if row.prompt == OLD_DEFAULT_PROMPT_STRING (snapshotted from pre-migration code):
    row.prompt = CALL_TOPICS_DEFAULT_PROMPT
    count_migrated += 1
  else:
    # user has customized — preserve as-is
    count_preserved += 1
logger.info(f"Migrated {count_migrated} call_topics prompts; preserved {count_preserved} customized rows.")
```

The `OLD_DEFAULT_PROMPT_STRING` is snapshotted from the current hardcoded fallback text at `topics_service.py:284-299` (*"You are an expert at analysing business call transcripts. Extract every distinct topic discussed — be exhaustive …"*). Captured into a migration-only constant that gets deleted after release.

#### 4.6.4 UI affordances on the artifact type card

Three additions to `ArtifactTypeCard.tsx`:

1. **Expandable textarea** — prompt editor grows from today's ~120px height to ~500px when expanded. The multi-section default is ~40 lines; editing needs room.
2. **"Show runtime context" disclosure** — collapsed by default; when expanded shows a read-only preview of what the system appends at runtime:
   ```
   Project context: {projects.context}
   Existing project topic names:
     - {name 1}
     - {name 2}
   Transcript: {transcript}

   Response schema: {JSON schema}
   ```
   With a helper line: *"These are added automatically at extraction time and cannot be edited here."*
3. **"Reset to default" button** — secondary button, confirmation dialog (*"Overwrite your current prompt with the latest default? Your edits will be lost."*), calls the endpoint from §4.6.2.

#### 4.6.5 Applies to all four prompt categories

The same single-source-of-truth pattern extends to the other three categories (per §7 Q4 resolution):
- `backend/prompts/artifacts.py` — `DEFAULT_ARTIFACT_PROMPT` (per-type varies; keep per-type constants)
- `backend/prompts/merge_verification.py` — `MERGE_VERIFICATION_DEFAULT_PROMPT`
- `backend/prompts/not_discussed_check.py` — `NOT_DISCUSSED_DEFAULT_PROMPT`

Each with the same three-touchpoint pattern (seed / fallback / reset endpoint) and the same migration strategy for existing unedited rows. Story scope: do this for `call_topics` first (primary goal), then extend to the others in the same implementation pass since the mechanism is identical.

## 5. Implementation plan preview

*Detailed plan lives in the implementation plan doc after this spec is approved. Below is the shape to scope.*

**Backend — schema**
1. DB migration — add `is_parked BOOL DEFAULT FALSE`, `open_questions JSONB DEFAULT '[]'::jsonb`, `importance TEXT DEFAULT 'medium'`, `rationale TEXT DEFAULT ''` to `topic_updates`. (Fields live on `topic_updates`, not `topics` — match existing schema pattern.)
2. `TopicIn` / `TopicUpdate` Pydantic models — add four new optional fields. `importance: Literal["high", "medium", "low"] = "medium"`.

**Backend — prompt as single source of truth (§4.6)**
3. New module `backend/prompts/call_topics.py` exporting `CALL_TOPICS_DEFAULT_PROMPT: str` — the full multi-section default per §4.2. Also export `OLD_DEFAULT_PROMPT_STRING` for migration comparison (snapshot of pre-migration `topics_service.py:284-299`).
4. `topics_service.py` — replace the inline fallback string with `from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT`; `extract_call_topics` uses `stored_prompt or CALL_TOPICS_DEFAULT_PROMPT`. Update `_TOPIC_SCHEMA` to include the four new fields.
5. New DB migration — for each `artifact_types` row where `category='call_topics'` AND `prompt == OLD_DEFAULT_PROMPT_STRING`: update `prompt = CALL_TOPICS_DEFAULT_PROMPT`. Log migrated/preserved counts.
6. New endpoint — `GET /api/artifact-types/defaults/{category}` returning `{prompt, llm, model}` from the in-code constants. Used by the "Reset to default" button.
7. Parallel prompt modules for the other three categories (§4.6.5): `backend/prompts/artifacts.py`, `backend/prompts/merge_verification.py`, `backend/prompts/not_discussed_check.py`. Same three-touchpoint pattern, same migration logic with their respective old-default snapshots.

**Backend — OpenRouter integration**
8. DB migration — `ALTER TABLE artifact_types ADD COLUMN model TEXT`; `ALTER TABLE projects ADD COLUMN default_model TEXT`.
9. `llm_service.py` — add `openrouter` branch dispatching via `AsyncOpenAI` with `base_url=https://openrouter.ai/api/v1`. Add `model: str | None = None` kwarg to `generate_artifact`. Raise `ValueError` if `llm='openrouter'` and model is empty.
10. `routers/artifact_types.py` — `ArtifactTypeOut` / `ArtifactTypeCreate` / `ArtifactTypeUpdate` grow a `model` field. Seed `DEFAULT_ARTIFACT_TYPES` — `call_topics` entry becomes `llm='openrouter'`, `model='anthropic/claude-sonnet-4.6'`. Also update `artifacts`, `merge_verification`, `not_discussed_check` seeds per §4.4.4 table (Q4 resolution).
11. `routers/projects.py` — `ProjectOut` / `ProjectUpdate` grow `default_model`. `PATCH /projects/{id}` accepts the new field.
12. `routers/artifacts.py` + `topics_service.run_extraction_background` — resolve effective `model` (artifact-type override → project default → null) and pass to `generate_artifact`.
13. `backend/.env.example` — add `OPENROUTER_API_KEY=`. Update `README.md`.

**Backend — tests**
14. Rubric enforcement: canned transcript with fragmentation → assert consolidated output. Re-explanation filter: transcript with onboarding narration → zero topics from that segment. Anchor separation: mixed transcript → decisions / follow_up_items / open_questions each populated. Parked detection: "look at X later" → `is_parked=true`, no actions. Importance: all-4-criteria transcript → `importance="high"`.
15. Schema: round-trip `TopicIn` with new fields. Schema: artifact type create/update with `model` field.
16. LLM dispatch: `test_openrouter_dispatches_with_base_url_and_model`. Validation: `llm='openrouter'` without model raises ValueError. Unknown provider still raises ValueError.
17. Prompt single-source-of-truth: `DEFAULT_ARTIFACT_TYPES["call_topics"].prompt == CALL_TOPICS_DEFAULT_PROMPT`. Migration: rows matching `OLD_DEFAULT_PROMPT_STRING` → updated; customized rows → preserved.
18. Reset-to-default endpoint: `GET /api/artifact-types/defaults/call_topics` returns the constants exactly.

**Frontend — topic rendering**
19. `types/index.ts` — add `open_questions`, `is_parked`, `importance`, `rationale` to `TopicData`. Add `model` to `ArtifactType`. Add `default_model` to `Project`. Extend `LLMProvider` to include `'openrouter'`.
20. `CallTopicsStage.tsx` — rewrite `TopicRow` per §4.5 (three sections, parked variant, importance dot with tooltip).
21. `TopicEditor.tsx` / `TopicsDashboard.tsx` / `TopicsPanel.tsx` / `TopicEvidenceDrawer.tsx` — render new fields where existing topic data shows. Ripple edits only.

**Frontend — model picker & prompt editor (§4.4 + §4.6.4)**
22. New constant `MODEL_RECOMMENDATIONS` in `frontend/src/constants/models.ts` — per-category curated list (see §4.4.4 table) including labels, tiers, and slugs.
23. `ArtifactTypeCard.tsx` — five additions:
    - Replace current LLM radio with Provider dropdown (`Inherit / Groq / Claude direct / OpenAI direct / OpenRouter ⭐`)
    - Model dropdown visible only when provider is `openrouter`, populated from `MODEL_RECOMMENDATIONS[category]`, with "Custom…" free-text row at the bottom
    - Expandable prompt textarea (~120px → ~500px when focused or `[⤢]` clicked)
    - "Show runtime context" disclosure — read-only preview of system-appended blocks
    - "Reset to default" button — confirmation dialog, calls `GET /api/artifact-types/defaults/{category}` and populates the textarea
24. Project settings page — same two-control pattern for `default_llm` + `default_model`.
25. `ArtifactSelector.tsx` — reflect new provider label where LLM is summarised per artifact.

**Migration / rollout**
- Existing `topic_updates` rows get new-field defaults (`open_questions=[]`, `is_parked=false`, `importance='medium'`, `rationale=''`). No backfill LLM re-run — old topics render with empty new sections.
- Existing `artifact_types` rows: `model=null` works fine. `prompt` migrated if it matches `OLD_DEFAULT_PROMPT_STRING` per §4.6.3; customized prompts preserved.
- Existing `projects` rows: `default_model=null` — works, falls back to provider-implicit model.
- Feature is gated by the prompt + new fields being populated: old data continues to work; new extractions populate the new fields.

## 6. Tests

**Backend (pytest):**
- `test_extraction_rubric_consolidates_duplicates` — transcript with 3 REST-vs-GraphQL mentions → expects 1 topic covering all three.
- `test_extraction_drops_reexplanation` — transcript with 5 minutes of onboarding narration → zero topics from that segment.
- `test_extraction_separates_anchor_types` — mixed transcript → asserts decisions / follow_up_items / open_questions each populated correctly.
- `test_extraction_parks_future_items` — "we'll look at fat-tail modeling later" → `is_parked=true`, no actions.
- `test_schema_includes_new_fields` — round-trip `TopicIn` with new fields.
- `test_default_llm_for_call_topics_is_claude` — new projects seed `call_topics` with `llm='claude'`.

**Frontend (manual smoke, no e2e framework):**
- Render active topic with all three sections.
- Render parked topic — no Actions section, `⏸ PARKED` chip, Un-park button flips `is_parked`.
- Empty section rendering — topic with only decisions renders just the Decisions block.
- Edit mode — textareas for each section save correctly.

**Live validation:**
- Run extraction on 3 representative past calls from the RAMMMM project (user's current test bed). Compare old vs new output. User spot-checks for fragmentation, detail, coherence.

## 7. Open questions — resolved 2026-04-22

All open questions resolved with user sign-off:

1. ~~**Default model for `call_topics`.**~~ **Resolved**: `openrouter:anthropic/claude-sonnet-4.6` (§4.4).
2. ~~**Importance dot derivation.**~~ **Resolved**: Option (a) — LLM emits a structured `importance: "high"|"medium"|"low"` field. Encoded in §4.3 schema and §4.5 UI.
3. ~~**Where is `rationale` rendered?**~~ **Resolved**: Option (b) — hover tooltip on the importance dot. No permanent tile real estate.
4. ~~**Retrofit other prompts to OpenRouter?**~~ **Resolved**: Option (a) — switch all four categories' new-project seed defaults to OpenRouter per §4.4.4 table. Implementation step 10 covers this.
5. ~~**Prompt deployment mechanism.**~~ **Resolved**: single-source-of-truth Python constant, migration preserves customized rows, UI gets runtime-context disclosure + reset-to-default button. See §4.6.

## 8. References

- User rubric (verbatim source for §4.1): conversation turn 2026-04-22
- [Epic 10 Prompts Audit](./epic-10-prompts-audit.md) — Prompt 1 section, already flagged all these issues
- Current extraction implementation — [topics_service.py:261-341](../../../backend/services/topics_service.py#L261-L341)
- Current tile implementation — [CallTopicsStage.tsx:43-230](../../../frontend/src/components/CallTopicsStage.tsx#L43-L230)
