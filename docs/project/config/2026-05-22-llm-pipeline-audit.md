# LLM Pipeline Audit — call_topics → Pass ①②③

**Date:** 2026-05-22
**Status:** Analysis only — no solutions yet
**Goal:** map every LLM call in the flow with its inputs, expected output, known failure modes, and observed problems. Once we agree on the map, we'll decide where to fix.

---

## 1. The 4 LLM calls in the current pipeline

| # | Stage | Function | Why this call exists |
|---|---|---|---|
| **A** | `call_topics` | `extract_call_topics` | Extract a list of topics + tasks from a transcript |
| **B** | `project_updates` Pass ① | `run_verify_new` | For each "new" candidate, decide truly_new vs should_be_merged_with an existing topic |
| **C** | `project_updates` Pass ② | `run_verify_not_discussed` | For each existing topic NOT in the current call, confirm it really wasn't mentioned in the current transcript |
| **D** | `project_updates` Pass ③ | `run_extract_topic_updates` | For each merged topic, re-extract a citation-grounded snapshot + chronological evidence trail across all calls |

---

## 2. CALL A — Extract call_topics (v4 prompt)

### Inputs
- One transcript (current call only)
- The v4 prompt body (`backend/prompts/call_topics.py`)
- Project-level context if set

### Output expected
A JSON array of topics. Each topic:
```
{
  name, importance,
  tasks: [
    { task, next_step, status, owner,
      key_terms: [...],            # per task
      open_questions: [...],        # per task
      decisions: [...],             # per task
      citations: [...verbatim...]   # per task, ≥2 quotes
    }
  ]
}
```

### Guarantees we EXPECT
1. **Completeness** — every meaningful subject in the transcript becomes a topic
2. **Determinism** — same transcript → same topics
3. **Verbatim citations** — quotes literally copy-pasted from the transcript
4. **Per-task isolation** — task X's key_terms anchor THAT task, not others
5. **No invention** — no facts beyond what the transcript says

### Guarantees we actually have
| Guarantee | Reality |
|---|---|
| Completeness | ❌ Not guaranteed. Different runs miss different topics. User-observed: Stress Tests sometimes extracted, sometimes not, on the same transcript. |
| Determinism | ❌ LLM is stochastic (temperature unknown — likely default 0.7). |
| Verbatim citations | 🟡 Partially. v4 prompt asks for verbatim but ~50% of citations fail verbatim verify in practice. |
| Per-task isolation | ✓ Mostly OK with v4 prompt — each task has its own bag. |
| No invention | 🟡 Mostly. Occasional paraphrasing in citations. |

### Failure modes observed
- Missing topics (Stress Tests example) → cascades downstream
- Citation paraphrase (caught by our verbatim check, fails verify)
- Topic granularity inconsistency (sometimes 1 big topic, sometimes 3 small ones for the same subject area)

### Open questions
- What temperature is `_call_llm` using?
- Should we run a recall pass to catch missed topics?
- Should we use a higher-quality model (Claude vs DeepSeek)?
- How to enforce stable topic-name conventions across runs?

---

## 3. CALL B — Pass ① verify_new_topic

### Inputs
- One candidate topic (a topic Call N flagged as "new" — not matched in project_matching)
- 0–3 "qualified" existing project topics (filtered by mechanical pre-check)
- The PAST transcripts (calls 1..N-1)
- The v4-task-centric verify_new prompt (`backend/prompts/verify_new_topic.py`)

### Output expected
```
{
  evaluations: [{ topic_id, topic_name, task_fit: yes|no, reason }],
  final_verdict: "truly_new" | "should_be_merged_with",
  matched_topic_id, matched_topic_name,
  merge_reasoning,
  citations: [...verbatim from past transcripts...],
  extraction_grounded, ungrounded_items
}
```

### Guarantees we EXPECT
1. **Compare per-task** — candidate.tasks[] vs existing.tasks[] across 5 dimensions (task text, key_terms, OQ, decisions, citations)
2. **No false merge on platform-name-only overlap** (Snowflake X ≠ Snowflake Y)
3. **No false truly_new when content existed in past transcripts** — even if past extraction missed it
4. **Verbatim citations** to support merge verdicts
5. **Reasoning references concrete content** (≥2 dimensions referenced)

### Guarantees we actually have
| Guarantee | Reality |
|---|---|
| Compare per-task | ✓ Implemented. `_shape_topic_for_llm` sends per-task only. Prompt updated to require 5-dimension comparison. |
| No false merge on platform name | 🟡 Post-LLM check on rare-term citations + sanity flag, but LLM can still output bad reasoning. |
| **No false truly_new when content in past transcripts** | ❌ **KEY GAP.** Pass ① compares candidate vs past TOPICS, not vs past TRANSCRIPTS directly. If past extraction missed a topic, Pass ① has no chance of finding the connection. User-observed: Stress Tests false truly_new. |
| Verbatim citations | 🟡 Verified post-LLM; merge downgraded if <2 verbatim verified. |
| Reasoning task-anchored | 🟡 Post-LLM check parses reasoning for task references; downgrades if vague. |

### Failure modes observed
- 70% / 70% / 35% disparity on topics from the same content (user observation)
- LLM sometimes returns bare evaluations list instead of wrapped dict (DeepSeek quirk)
- Extraction-recall gap: candidate flagged truly_new despite the subject existing in past transcripts (because past extraction missed it)

### Open questions
- Should we compare candidate against past TRANSCRIPTS (full text search of key_terms), not just past topics?
- How do we distinguish "truly new" from "discussed before but missed at extraction"?
- Is the confidence % capturing the right uncertainty?

---

## 4. CALL C — Pass ② verify_not_discussed

### Inputs
- One existing project topic (its name + key_terms only — minimal anchor)
- The CURRENT call's transcript (only)
- The verify_not_discussed prompt (`backend/prompts/verify_not_discussed.py`)

### Output expected
```
{
  verdict: "not_discussed" | "actually_discussed",
  citation: null | { call_id, lines, quote }
}
```

### Guarantees we EXPECT
1. **Recall** — if the topic was mentioned anywhere in the current transcript, catch it
2. **Verbatim citation** when found
3. **No false "actually_discussed"** on tangential mentions

### Guarantees we actually have
| Guarantee | Reality |
|---|---|
| Recall | ❓ Untested at scale — we don't know the false-negative rate. |
| Verbatim citation | 🟡 Verified post-LLM but only 1 citation required (vs 2 for Pass ①). |
| No false actually_discussed | ❓ Not measured. |

### Failure modes observed
- We haven't reworked Pass ② UX yet (user noted this earlier)
- The 1-citation threshold may be too lax
- No mechanical pre-check (unlike Pass ①) — every existing-topic-not-in-call goes through LLM

### Open questions
- Same as Pass ①: what about TRANSCRIPT scan as deterministic signal before the LLM?
- Should Pass ② input richer data (existing topic's tasks too, not just name + key_terms)?

---

## 5. CALL D — Pass ③ extract_topic_updates

### Inputs
- One existing project topic (anchor: name, key_terms)
- ALL past transcripts (calls 1..N) for that project
- The extract_topic_updates prompt (`backend/prompts/extract_topic_updates.py`)

### Output expected
```
{
  extracted_snapshot: {
    summary, status,
    tasks: [{ task, next_step, owner, status,
              key_terms, open_questions, decisions,
              primary_citation, supporting_citations }],
    open_questions: [...], decisions: [...]
  },
  evidence_trail: [{ call_id, citation, action_label }]
}
```

### Guarantees we EXPECT
1. **Re-extract from transcripts** (not from prior extracted topics — to fix the extraction gap)
2. **Chronological evidence trail** (when each task/OQ/decision first appeared, was modified, was closed)
3. **Per-task ownership** of key_terms / OQ / decisions / citations
4. **Verbatim citations**

### Guarantees we actually have
| Guarantee | Reality |
|---|---|
| Re-extract from transcripts | ✓ Schema is correct |
| Chronological evidence trail | ✓ Output schema includes evidence_trail |
| Per-task ownership | 🟡 Prompt updated (Phase 4 of the task-centric refactor) but not yet tested with real data |
| Verbatim citations | 🟡 Same verbatim-check as Pass ① |

### Failure modes observed / suspected
- Pass ③ has not been exercised at scale yet (user hasn't reached this step)
- The chronological narrative is hard for the LLM (which transcript does the task appear in first? was it modified?)

### Open questions
- Should Pass ③ also do recall (check if any tasks NOT in the input but evident in transcripts)?
- How to validate the chronological_narrative is correct?

---

## 6. The KEY GAP across all 4 calls

**Issue:** the pipeline assumes Call A's extraction is the source of truth. Pass ①②③ all compare against the extracted topic set. If extraction misses a topic, all downstream passes inherit the gap.

**Specific user-observed symptoms:**
1. Same transcript loaded twice → different topic lists (Stress Tests inconsistency)
2. Pass ① confidence asymmetry (70% / 70% / 35%) — because the comparison set is unstable
3. No way to detect "this topic existed in past but past extraction missed it"

**Possible directions** (analysis only — no commitment):
- A. Stabilize CALL A (lower temperature, deterministic prompting, better model)
- B. Add a recall step to CALL A (2nd LLM call asking "did we miss anything?")
- C. Add a transcript-mention check to Pass ① (deterministic — count key_term occurrences in past transcripts as a separate signal)
- D. Make confidence reflect extraction quality (penalize when key_terms appear in past transcripts but no past topic)
- E. Allow the user to UPLOAD a topic dictionary that defines the project's known major subjects upfront (taxonomy guides extraction)

We need to decide which combination addresses the user's actual experience without bloating the pipeline.

---

## 7. Questions for the user

Before designing solutions:

1. **On the Stress Tests example** — when you say "the SAME transcript was uploaded twice", was the result:
   - 2 different topic lists for the same transcript content (extraction non-determinism)?
   - OR 2 calls each with their OWN transcript subset, and one of them genuinely doesn't discuss Stress Tests in its portion?

2. **On Pass ① confidence** — is the problem "70% on topic X feels too high/low given what I know"? Or "the % swings wildly from run to run on the same data"?

3. **What's your acceptance threshold** — for matching to be useful, you need to trust at what % of confidence? 90%+? 70%+?

4. **Do you have a known list of major subjects** for a project — a taxonomy you'd be willing to maintain that the LLM should use as a checklist? (This unlocks direction E.)

5. **Token budget concerns** — would you accept doubling the LLM cost per call to gain reliability (recall pass + transcript-mention check)?
