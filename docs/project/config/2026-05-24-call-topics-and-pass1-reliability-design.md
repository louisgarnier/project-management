# Call Topics (v5) + Pass 1 Reliability Rework — Design

**Date:** 2026-05-24
**Author:** brainstorm session (Louis + Claude)
**Status:** Draft — awaiting user review before plan
**Supersedes context:** project_matching stage will be removed; this design assumes that simplification
**Out of scope:** Pass 2 (verify_not_discussed), Pass 3 (extract_updates)

---

## 1. Why this exists

On 2026-05-23 the user ran a controlled test: load the same transcript into call A and call B of the same project, force all call B topics to "new" at the matching stage, run Pass 1. Expected result: clean reconciliation (all candidates flagged as duplicates of existing project topics).

Actual result (5 candidates):
- 1 LLM crash (non-dict response, defaulted to truly_new)
- 1 false negative (truly_new when should have merged)
- 2 correct merge verdicts crippled to 38% confidence by citation verification failures
- 1 questionable "mega-topic" candidate with 15 tasks spanning multiple work streams

This test surfaced not one bug but a layered architectural problem.

## 2. The meta-pattern (why prior fixes failed)

Walking the build log: every previous attempt at cross-call coherence (EPIC-15 chronology v1, EPIC-15 chronology v2, EPIC-16 Pass 1 with citation contract) failed in the same way — **asking the LLM to be the source of truth for deterministic work** (verbatim quotes, byte-perfect IDs, exhaustive cross-call reasoning).

The only thing in this family that worked was **v5 extraction** (EPIC-17), specifically because it inverted the responsibility: LLM does cognitive work, code does mechanical work.

This design follows that lesson. Every change either moves deterministic work to code, narrows LLM context, or strengthens the data layer the LLM operates against.

## 3. Root causes (verified by code reading, not inferred)

### RC1 — Two stores out of sync
`topic_registry` (loaded by v5 Stage 1) and `project_topics` (loaded by Pass 1 via `_get_previous_topics`) are separate stores. Stage 5 clusters against registry names with no visibility into the structure under each. Pass 1 evaluates against the full structure. The gap creates inconsistent matching.

### RC2 — Stage 5 clusters blind
`call_topics_v5_cluster.py:21` shows Stage 5 receives only canonical topic names + one-line descriptions. No tasks, no key_terms, no structure. Forced to guess the right canonical name from semantically thin input. This is the primary cause of the "mega-topic" symptom (Topic 2 in the test) and the false-negative split-into-new-topic symptom (Topic 5).

### RC3 — Pass 1 verbatim quoting is architecturally fragile
Pass 1 asks the LLM to copy-paste verbatim quotes (`verify_new_topic.py:CITATION CONTRACT`). DeepSeek paraphrases (collapses repeated filler, normalizes punctuation). The `quote in body` strict-substring check (`citation_verify.py:28`) rejects them. Every cited quote in the test failed verification. v5 already solved this for extraction via line-number citations — Pass 1 just didn't inherit the pattern.

### RC4 — extraction_grounded check is asking the LLM to verify against data it doesn't have
`verify_new_topic.py:128-131` instructs the LLM to check items against the *current* call's transcript. But Pass 1 only sends *past* transcripts (`routers/topics.py:688`). The LLM hallucinates grounding flags. Topic 2's noisy ungrounded-items dump came from this bug.

### RC5 — v5 canonical matches are not verified anywhere
Stage 5's canonical match (cluster name == registry name, case-insensitive) is made on name lookup alone. If wrong, no downstream check. Pass 1 only sees the "new" candidates. Wrong canonical matches silently corrupt project_topics.

### RC6 — Three independent similarity implementations
Stage 6 (Jaccard, threshold 0.6), Pass 1 lexical_precheck (IDF Jaccard, threshold 0.15), and the old project_matching had their own. Inconsistent treatment of the same topic pair across stages.

### RC7 — `projects.context` field exists but is not used in any LLM prompt
`stage_1_context.py:76` loads it. No call sites consume it. The single highest-leverage priming signal we have is being thrown away.

### RC8 — Architectural co-defaults baked into call sites
Stage 5 and Stage 7 hardcode `model="deepseek/deepseek-v3.2"` in function signatures (`stage_5_cluster.py:103`, `stage_7_synthesis.py:106`). Project's `default_llm` / `default_model` is not consulted at extraction time. Dev/prod divergence baked into code.

---

## 4. Scope

**In:** Changes to v5 call_topics pipeline (Stages 1–10) and Pass 1 (`verify_new`).

**Out (will inherit broken architecture until a future epic):**
- Pass 2 (`verify_not_discussed`)
- Pass 3 (`extract_updates` — chronology, EPIC-15's original goal)
- Retroactive topic split/merge UX
- Frontend topic browser / Kanban beyond the minimum needed to render new Pass 1 output

**Constraint:** must work on cheap LLM (DeepSeek) for dev iteration. Production may use Opus. Architecture must be model-agnostic.

---

## 5. Work streams

### STREAM 0 — Unify the data layer

**Goal:** Single source of truth for "project's topics + their tasks + their key_terms," consumed identically by v5 Stage 5 and Pass 1.

**Approach (to be confirmed in plan):**
- Make `topic_registry` a derived/projected view over the canonical project_topics store, OR collapse the two tables into one.
- Single read API (e.g., `get_project_topic_state(project_id) → list[ProjectTopic]`) returning shape `{topic_id, name, description, key_terms, tasks: [{task, next_step, key_terms, open_questions, decisions, ...}]}`.
- Stage 1 and Pass 1's `_get_previous_topics` both consume this API.

**Deliverables:**
- Migration (if schema change)
- New service module `backend/services/project_topic_state.py`
- Stage 1 + Pass 1 refactored to consume it

**Acceptance:** identical query returns identical state to both consumers; no schema drift possible.

---

### STREAM 1 — call_topics (v5) extraction changes

**S1.1 — V5-CORE: Stage 5 receives full structure**

Stage 5's prompt currently lists canonical names only. New version receives the structure from STREAM 0:

```
PROJECT TOPICS (controlled vocabulary — prefer matching to these):

- ARM
  Description: Account aggregation risk modeling work stream
  Existing tasks:
    - Test LMAC vs Monte Carlo Mac on fixed income portfolio (Mark)
    - Investigate Monte Carlo Mac job memory failure (Mark)
    - Determine optimal risk model for stress test (Hassan)
  Key terms: LMAC, Monte Carlo, MAC, memory, fixed income, stress test
```

LLM matches new units against real structure ("this LMAC discussion fits the existing 'Test LMAC vs Monte Carlo Mac' task → cluster under ARM") instead of guessing from topic names. Eliminates the "mega-topic" and false-canonical-match failure modes at the source.

**S1.2 — V5-CONTEXT: wire `projects.context` into Stage 5 and Stage 2**

Verify current consumption (likely zero). If unused, inject project context into Stage 2 (atomic extraction) and Stage 5 (clustering) system prompts as priming. Format TBD — short paragraph, not a wall.

**S1.3 — V5-MEASURE: gold-set regression test**

Same-transcript stability test against the existing gold set (`docs/project/config/gold set/`). Run Stages 2, 5, and 7 N times each (N=3 minimum, temp=0). Compare:
- Stage 2: same unit set produced across runs?
- Stage 5: same unit-to-topic assignment?
- Stage 7: same task synthesis?

Report drift quantitatively. Establish baseline numbers. Used as regression gate for S1.1 and S1.2.

**S1.4 — V5-MODEL-CONFIG: route through project config**

Remove hardcoded `model="deepseek/deepseek-v3.2"` defaults from Stage 5 and Stage 7. Read `project.default_llm` / `project.default_model` at orchestrator level. Tests can still override; production paths use config.

---

### STREAM 2 — Pass 1 reliability changes

**S2.1 — P1-CITATIONS: port v5's line-number pattern**

Replace Pass 1's free-form quote citation contract with line-number citations:

- Line-number past transcripts before constructing the Pass 1 prompt (reuse v5 Stage 0 ingest)
- Prompt asks LLM to emit `{"call_id": ..., "evidence_lines": [start, end]}` per cited piece of evidence
- Drop the `quote` field from the LLM output schema
- New code path resolves `evidence_lines` → verbatim text (mirror of v5 Stage 4)
- Verifier becomes a bounds check (`start ≤ end ≤ line_count`) + non-empty resolved text, not a string match

LLM stops being responsible for verbatim quoting. Model-agnostic.

**S2.2 — P1-BIDIRECTIONAL: verify v5's canonical matches too**

Pass 1 input expands. For each topic v5 produced:
- If `new_topic=true` → existing logic: verify against project topics, verdict ∈ {truly_new, should_be_merged_with}
- If `new_topic=false` (canonical match) → new logic: verify the match was correct. Verdict ∈ {confirmed_match, wrong_canonical_actually_new, wrong_canonical_belongs_elsewhere}

A wrong canonical match becomes a structured signal, not silent corruption. UI distinguishes the two verdict tracks.

**S2.3 — P1-CLEANUP**

- Drop `extraction_grounded` and `ungrounded_items` from the prompt schema and the result handler (RC4)
- Harden non-dict LLM response: if LLM returns bare array, wrap or fail cleanly (Stage 5 v5 pattern); don't burn two retries on the same malformed shape
- Unify similarity scoring: Stage 6 and Pass 1's `lexical_precheck` use the same implementation + same threshold. Extract to `backend/services/topic_similarity.py`. Single source of truth.

**S2.4 — P1-RETRIEVAL (deferred, conditional)**

Refactor Pass 1 from "one mega-prompt over all topics + all transcripts" to "top-K mechanical ranking, then K focused per-pair LLM calls." Each focused call gets one candidate + one existing topic + only the transcript line ranges relevant to that topic.

**Gating:** only build this if S1.1 + S2.1 + S2.2 don't reach acceptable confidence on the same-transcript test. Defer otherwise. Treat as known follow-up.

---

### STREAM 3 — Pass 1 test fixture

**Goal:** iterate Pass 1 without burning LLM budget or running the whole pipeline.

Hand-authored JSON fixtures under `backend/tests/fixtures/pass1/`:
- `candidate_topic.json` — one v5-output topic with realistic per-task shape
- `project_topics.json` — list of existing project topics in the new unified shape
- `past_transcripts.json` — line-numbered past transcript bodies
- `ground_truth_verdict.json` — expected verdict + matched_topic_id + minimum confidence

Test scenarios at minimum:
- Same-transcript dup (every candidate should reconcile)
- True new (no overlap)
- Mega-topic (candidate spans multiple existing topics)
- Wrong canonical (v5 says canonical=ARM but it's actually about a different work stream)
- Naming drift (semantically same, lexically different)

Pass 1 unit tests against fixtures + mocked LLM (returns canned responses keyed by prompt fingerprint). Real-LLM smoke tests run on demand, not in CI.

---

### STREAM 4 — Verification asymmetry in Pass 1 UX

Reflect the "wrong merge collapses; wrong new is reversible" asymmetry in the workflow:
- `truly_new` at confidence ≥ threshold → auto-accept (no human review)
- `should_be_merged_with` always requires human click, regardless of confidence
- `wrong_canonical_*` from S2.2 always requires human click
- Threshold value to be calibrated against fixture results (likely 70–80%)

UI changes scoped to the Pass 1 review screen only.

---

### STREAM 5 — Migration: cached results + frontend

**Cached results:** existing `verify_new_cache` JSONB blobs have the old schema (free-form quote citations, `extraction_grounded` field, etc.). Two options to evaluate in the plan:
- **(a) Versioned cache:** add `schema_version` field; reader handles v1 + v2; old cached results render in legacy mode
- **(b) One-shot reprocess:** add a backfill script that re-runs Pass 1 for all calls with `verify_new_status='done'`; old cache discarded

Recommendation (to confirm): (b) is cleaner and only costs ~one LLM call per historical call.

**Frontend:** coordinate Pass 1 output schema changes with `EvidenceTrail.tsx`, `TopicCitationBadge.tsx`, `ProjectUpdatesStage.tsx` updates. Frontend ships in the same release as the backend; no shim layer.

---

## 6. Topic lifecycle (narrow — v5 + Pass 1 touchpoints only)

After v5 + Pass 1 process a call, project_topics is updated as follows:

| v5 verdict | Pass 1 verdict | DB write |
|---|---|---|
| `new_topic=false` (canonical) | `confirmed_match` | append `topic_updates` row tied to existing project_topic |
| `new_topic=false` (canonical) | `wrong_canonical_actually_new` | discard the canonical link; treat as `truly_new` path → create new project_topic |
| `new_topic=false` (canonical) | `wrong_canonical_belongs_elsewhere` | append `topic_updates` row tied to the corrected project_topic |
| `new_topic=true` (provisional) | `truly_new` | create new project_topic in unified store (STREAM 0) — one write, not two |
| `new_topic=true` (provisional) | `should_be_merged_with` | append `topic_updates` row tied to the matched project_topic (Pass 1 picks the target, same logic as today); discard provisional name |
| `new_topic=true` (provisional) | `wrong_canonical_belongs_elsewhere` is N/A | (this verdict only applies when v5 made a canonical match — i.e. `new_topic=false`) |

Pass 2/3 lifecycle (archival, chronology) explicitly out of scope.

---

## 7. Work order + dependencies

```
S1.3 V5-MEASURE (baseline drift on current code — pure measurement, no deps)
  │
  ▼
STREAM 0 (data layer — foundation for everything that follows)
  │
  ├──→ S1.1 V5-CORE (needs STREAM 0's unified shape)
  │      └──→ S1.2 V5-CONTEXT, S1.4 V5-MODEL-CONFIG (independent after S1.1)
  │
  ├──→ STREAM 3 (Pass 1 test fixtures — need STREAM 0 shape)
  │      └──→ enables fast iteration on STREAM 2
  │
  └──→ STREAM 2 (Pass 1: S2.1, S2.2, S2.3 — independent after STREAM 0)
         └──→ S2.4 conditional, only if S1+S2 base doesn't suffice
                │
                └──→ STREAM 4 (UX asymmetry — Pass 1 must be stable first)
                       │
                       └──→ STREAM 5 (migration — last)
```

**Ship order:** S1.3 (baseline) → STREAM 0 → STREAM 1 (S1.1, then S1.2/S1.4 in parallel) → STREAM 3 → STREAM 2 → STREAM 4 → STREAM 5.

Re-run S1.3 after S1.1 lands to measure the delta and validate V5-CORE's effect on drift.

---

## 8. Open questions for the implementation plan

1. **Schema unification approach for STREAM 0:** view-over-existing vs. table merge. Needs a quick spike to evaluate migration cost.
2. **`projects.context` current usage:** grep to confirm whether it's actually unused before claiming S1.2 is a free win.
3. **Stage 11 human approval workflow interaction:** S2.2 (P1-BIDIRECTIONAL) introduces new verdict states. Does Stage 11 need updates, or does Pass 1's review screen subsume that role for canonical match verification?
4. **Confidence threshold for STREAM 4 auto-accept:** value to calibrate after S1+S2 ship and we have fixture-driven numbers.
5. **P1-RETRIEVAL gating criteria:** what reliability number tells us we DON'T need S2.4? Suggest: same-transcript test on fixture reaches ≥90% correct verdicts at ≥75% confidence.
6. **DB migration cost for STREAM 5:** one-shot reprocess vs. versioned cache — depends on how many historical calls have cached Pass 1 results.

---

## 9. What this design does NOT promise

- **Pass 2 and Pass 3 stay architecturally broken** until a future epic. The citation pattern fix is Pass 1 only.
- **Chronology** (EPIC-15's original goal — coherent cross-call topic evolution narratives) is NOT in scope. Pass 3 is the closest surviving piece and it's untouched.
- **Frontend topic browser overhaul** beyond the minimum needed to render new Pass 1 output is out of scope.
- **Retroactive split/merge** (user realizes 6 calls later that "ARM" was actually 2 separate workstreams) is not addressed.

---

## 10. Acceptance criteria

This design is considered shipped when:

1. **Same-transcript test passes:** Load identical transcript into 2 calls of the same project. After v5 + Pass 1 run on call B, ≥90% of candidates verdicted as merges (or `confirmed_match` for canonical paths) at confidence ≥75%. No citation verification failures.
2. **Gold-set drift baseline established:** S1.3 produces a measurable drift number for Stages 2/5/7 that V5-CORE demonstrably reduces.
3. **Pass 1 fixtures green:** all scenarios in STREAM 3 pass with mocked LLM and on the configured project LLM.
4. **No regressions:** existing backend tests (`pytest backend/tests/`) green; frontend `npx tsc --noEmit` + lint clean.
