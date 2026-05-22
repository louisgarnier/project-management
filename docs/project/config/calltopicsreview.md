# PRD — Call Topics Extraction Pipeline

## Context

The current call topics extraction system relies on a single-shot LLM call (v4 prompt) to perform topic discovery, task extraction, citation generation, schema filling, and prioritization simultaneously. This produces unstable recall (topics randomly missed across runs), non-deterministic outputs (no temperature control), partially verbatim citations (~50% verify failure rate), and inconsistent topic naming across calls within the same project.

This PRD defines the target architecture: a multi-stage extraction pipeline where each LLM call performs a narrow, well-defined cognitive task, and deterministic code handles bookkeeping (citation resolution, validation, registry management). The architecture is designed to be built once and not require rearchitecting as scale or quality requirements grow.

## Goals

- **Recall**: every meaningful subject in the transcript is extracted, reproducibly across runs.
- **Determinism**: same transcript → same output. Temperature 0 everywhere.
- **Verbatim citations**: 100% of citations match transcript text exactly, by construction.
- **Naming stability**: the same subject gets the same topic name across calls within a project.
- **Auditability**: every claim in the output traces back to specific transcript line ranges.
- **Measurability**: pipeline changes are evaluated against a gold set, not by impression.

## Non-goals

- Real-time / streaming extraction.
- Multi-language support (English only initially).
- Multi-hour transcripts exceeding Opus 4.7 context window (additive change later if needed; not in scope here).
- Replacing the call-tracking app's BM25/RAG layer (this pipeline feeds into it, not vice versa).

## Target output

The output schema remains compatible with the current v4 contract:

```json
[
  {
    "topic_name": "Stress Testing",
    "importance": "high",
    "tasks": [
      {
        "task": "...",
        "next_step": "...",
        "owner": "...",
        "status": "...",
        "key_terms": ["..."],
        "open_questions": ["..."],
        "decisions": ["..."],
        "citations": ["...verbatim quote..."],
        "confidence": 0.91
      }
    ]
  }
]
```

`confidence` is a new field. All others match current behavior.

---

## Pipeline overview

| # | Stage | Mechanism | Model |
|---|-------|-----------|-------|
| 0 | Transcript ingestion | Code | — |
| 1 | Project context loading | Code | — |
| 2 | Atomic unit extraction | LLM | Opus 4.7 |
| 3 | Adversarial recall pass | LLM | Opus 4.7 |
| 4 | Citation resolution | Code | — |
| 5 | Topic clustering | LLM | Opus 4.7 |
| 6 | Topic registry reconciliation | Code + human | — |
| 7 | Per-topic task synthesis | LLM (per topic) | Opus 4.7 |
| 8 | Task-level citation attachment | Code | — |
| 9 | Confidence scoring | Code | — |
| 10 | Validation | Code | — |
| 11 | Human review interface | UI | — |
| 12 | Final output serialization | Code | — |
| 13 | Evaluation harness (offline) | Code | — |

---

## Stage specifications

### Stage 0 — Transcript ingestion

**Mechanism**: deterministic code. No LLM.

**Input**: raw transcript file.

**Processing**:
- Parse transcript into ordered lines.
- Normalize speaker names (consistent casing, strip honorifics if inconsistent).
- Strip ASR artifacts (duplicated tokens, filler markers — configurable).
- Assign every line a stable integer index, zero-padded to 4 digits.

**Output**: numbered transcript object where every line is addressable by `[NNNN]`.

**Acceptance**:
- Line indices are stable across re-runs.
- Every original utterance is preserved (no silent drops).
- Line index → line text lookup is O(1).

---

### Stage 1 — Project context loading

**Mechanism**: deterministic code. No LLM.

**Input**: project identifier (e.g. RAM/SWIB, NWM).

**Processing**:
- Load project metadata (engagement name, stakeholders, current phase).
- Load project topic registry — the controlled vocabulary of canonical topic names accumulated from prior calls.
- For new projects, registry is empty.

**Output**: context bundle = `{project_metadata, topic_registry}`.

**Acceptance**:
- Missing registry returns empty list, not error.
- Registry is project-scoped; no cross-project leakage.

---

### Stage 2 — Atomic unit extraction

**Mechanism**: LLM call. Claude Opus 4.7. Temperature 0.

**Input**: numbered transcript + context bundle.

**Processing**:
The model extracts every meaningful atomic unit from the transcript. No topic grouping at this stage. Each unit is one of:
- `task` — something to be done
- `decision` — something decided
- `question` — open question raised
- `blocker` — impediment identified
- `statement` — notable statement worth tracking

Each unit must include:
- `unit_id`: deterministic identifier (e.g. `u_0001`)
- `type`
- `text`: paraphrased description
- `owner`: speaker or assigned person, or `"unassigned"`
- `evidence_lines`: `[start, end]` transcript line range

**Prompt requirements**:
- Optimize for recall, not organization.
- Do not summarize. Do not group. Do not deduplicate.
- Every unit anchored to line range(s).

**Output**: flat list of atomic units.

**Acceptance**:
- Output is valid JSON conforming to the unit schema.
- Every unit has a valid `evidence_lines` range within transcript bounds.
- Temperature is 0; model and parameters logged on every call.

---

### Stage 3 — Adversarial recall pass

**Mechanism**: LLM call. Claude Opus 4.7. Temperature 0.

**Input**: full numbered transcript + list of atomic units from Stage 2.

**Processing**:
The model reviews the transcript against the extracted units and identifies missed atomic units only. Returns the same unit schema. New `unit_id` values assigned, continuing the sequence from Stage 2.

**Prompt requirements**:
- Critique-mode framing: "What was missed?"
- Return only new units. Do not re-emit existing ones.
- Return empty list if nothing missed.

**Output**: list of additional atomic units, merged into the Stage 2 pool to form the complete atomic unit pool.

**Acceptance**:
- Recall pass runs unconditionally (not skipped if Stage 2 looks complete).
- Merged pool has no duplicate `unit_id`s.
- Gold-set evaluation shows recall improvement versus Stage 2 alone.

---

### Stage 4 — Citation resolution

**Mechanism**: deterministic code. No LLM.

**Input**: atomic unit pool with `evidence_lines` references + numbered transcript.

**Processing**:
For every unit, resolve `evidence_lines` to actual transcript text. Attach as `citation` field. The LLM never generates the citation string; code copies it from the source.

**Validation**:
- Line ranges within transcript bounds.
- Resolved citation is non-empty.
- Units failing validation are flagged but not dropped (handled in Stage 10).

**Output**: atomic unit pool with verbatim `citation` strings attached.

**Acceptance**:
- 100% of citations are byte-for-byte identical to the corresponding transcript lines.
- No LLM call in this stage.

---

### Stage 5 — Topic clustering

**Mechanism**: LLM call. Claude Opus 4.7. Temperature 0.

**Input**: complete atomic unit pool + project topic registry.

**Processing**:
The model groups atomic units into topics. Each unit belongs to exactly one topic. For each topic:
- Prefer an existing registry name if any registry topic fits the cluster.
- Only propose a new topic name if nothing in the registry matches.
- Flag new proposals with `new_topic: true`.

**Prompt requirements**:
- Registry is provided in-context as preferred vocabulary.
- Output format: `[{topic_name, unit_ids: [...], new_topic: bool, importance: low|medium|high}]`.
- Every `unit_id` from the pool must appear in exactly one topic.

**Rationale for LLM over embeddings**: domain-specific vocabulary (SAAM/TAA, EDS+/S07, FX Outrights, share class hedging) is poorly served by generic embedding similarity. LLM-with-registry-in-context produces better cluster boundaries for specialized work.

**Output**: topic groupings over the atomic unit pool.

**Acceptance**:
- Every atomic unit appears in exactly one topic (no orphans, no duplicates).
- Topics named from the registry use the exact canonical string.
- New topic proposals are flagged.

---

### Stage 6 — Topic registry reconciliation

**Mechanism**: deterministic code + human approval gate. No LLM.

**Input**: topic groupings from Stage 5 + current registry.

**Processing**:
- For topics matched to registry → finalize canonical name.
- For topics flagged `new_topic: true` → hold for human approval (Stage 11).
- Build the working topic list for downstream stages, using canonical names for matched topics and provisional names for new topics pending approval.

**Output**: topics with finalized or provisional names + queue of new topic proposals for human review.

**Acceptance**:
- No automatic registry mutation. New topics enter the registry only via human approval.
- Provisional names are visually distinguishable from canonical ones in downstream stages.

---

### Stage 7 — Per-topic task synthesis

**Mechanism**: one LLM call per topic. Claude Opus 4.7. Temperature 0.

**Input** (per topic): atomic units assigned to that topic + their citations + the task schema.

**Processing**:
The model synthesizes the atomic units into structured task objects. Because the recall problem and clustering problem are already solved, this is a focused, narrow-context task. Each task includes:
- `task`, `next_step`, `status`, `owner`
- `key_terms`, `open_questions`, `decisions`
- `evidence_unit_ids`: references back to the atomic units that support this task

**Prompt requirements**:
- Schema matches existing v4 output.
- Every task must reference at least 2 evidence units.
- Per-task isolation: a task's `key_terms`, `open_questions`, and `decisions` anchor that task only.

**Output**: structured task objects per topic.

**Acceptance**:
- Output conforms to v4-compatible task schema.
- Every task has ≥2 `evidence_unit_ids`.
- Per-topic context window is narrow (only that topic's units, not the full transcript).

---

### Stage 8 — Task-level citation attachment

**Mechanism**: deterministic code. No LLM.

**Input**: tasks with `evidence_unit_ids` + atomic unit pool with citations.

**Processing**:
For each task, walk `evidence_unit_ids`, collect citations from the referenced atomic units, attach to the task's `citations` field. Enforce minimum 2 citations per task.

**Output**: tasks with verbatim citations attached.

**Acceptance**:
- Citations on tasks are byte-identical to citations on the source atomic units.
- Tasks with fewer than 2 citations are flagged for Stage 10 validation.

---

### Stage 9 — Confidence scoring

**Mechanism**: deterministic code, heuristic. No LLM.

**Input**: tasks with attached citations + atomic unit pool.

**Processing**:
Compute a confidence score in [0.0, 1.0] for each task based on:
- Number of supporting atomic units (more → higher)
- Number of distinct speakers referencing the topic (more → higher)
- Owner clarity (explicit owner → higher, unassigned → lower)
- Citation count (more → higher, capped)
- Topic name source (registry → higher, new → lower)

Weights are configurable. Initial weights set heuristically and tuned against the gold set.

**Output**: tasks with `confidence` field.

**Acceptance**:
- Score is deterministic given the same inputs.
- Score correlates with human judgment on a sample of gold-set tasks.

---

### Stage 10 — Validation

**Mechanism**: deterministic code. No LLM.

**Input**: full extraction with topics, tasks, citations, confidence scores.

**Checks**:
- Every task has ≥2 verbatim citations matching transcript text exactly.
- Every citation line range is within transcript bounds.
- Every topic has ≥1 task.
- Every atomic unit is assigned to exactly one topic.
- No duplicate tasks within a topic (same owner + same `next_step` + overlapping evidence).
- No duplicate topic names within a single run.
- Every owner is non-empty string or explicit `"unassigned"`.

**On failure**:
- Log the failure with stage + unit/task/topic identifier.
- Retry the affected stage once.
- If still failing, surface to human review in Stage 11.

**Output**: validated extraction + validation report.

**Acceptance**:
- All checks are deterministic and re-runnable.
- Failures produce actionable diagnostics, not silent drops.

---

### Stage 11 — Human review interface

**Mechanism**: UI layer. No LLM.

**Input**: validated extraction + new topic proposals + low-confidence tasks + validation flags.

**Processing**:
Present to the user:
- **New topic proposals** (from Stage 6): approve / reject / merge with existing registry entry.
- **Low-confidence tasks** (from Stage 9, below configurable threshold e.g. 0.5): approve / edit / drop.
- **Validation flags** (from Stage 10): review and resolve.

**Output**: human-approved final extraction + registry updates (if new topics approved, they are added to the project's registry for future calls).

**Acceptance**:
- No registry mutation without explicit user approval.
- Approval actions are logged for audit.
- Default action on no-input is "hold" (nothing auto-approved).

---

### Stage 12 — Final output serialization

**Mechanism**: deterministic code. No LLM.

**Input**: human-approved extraction.

**Processing**:
Serialize into the v4-compatible JSON schema. Persist to wherever the call-tracking app reads from.

**Output**: final `call_topics` JSON.

**Acceptance**:
- Schema is v4-compatible (existing downstream consumers continue to work).
- `confidence` field is additive and ignored by consumers that don't use it.

---

### Stage 13 — Evaluation harness (offline)

**Mechanism**: deterministic code. No LLM. Not in production critical path.

**Input**: gold set of 5 hand-annotated transcripts with ground-truth topics and tasks.

**Processing**:
After any pipeline change (new prompt, new model, new heuristic, new weight), re-run the pipeline on the gold set and compute:
- Topic recall and precision
- Task recall and precision
- Citation validity rate (must be 100% by construction)
- Naming stability across re-runs (same transcript, different runs → same topic names)
- Confidence score correlation with human judgment

**Output**: evaluation report.

**Acceptance**:
- Gold set exists and is version-controlled.
- Evaluation script runs in < 5 minutes against the gold set.
- Pipeline changes are not merged without an evaluation report.

---

## Build order

The pipeline is the final architecture. Build order is sequenced so each component is independently testable against the gold set before the next is built.

1. **Foundation**: Stages 0, 1, 13 (ingestion, context loading, evaluation harness with gold set). Required before anything else can be measured.
2. **Recall layer**: Stages 2, 3, 4 (atomic extraction, recall pass, citation resolution). Validate against gold set: are atomic units complete and citations 100% verbatim?
3. **Organization layer**: Stages 5, 6 (clustering, registry reconciliation). Validate: do topics match expected names and groupings?
4. **Synthesis layer**: Stages 7, 8 (task synthesis, citation attachment). Validate: are tasks complete and well-formed?
5. **Operational layer**: Stages 9, 10, 11, 12 (confidence, validation, human review, serialization).

---

## Suggested epic breakdown

The pipeline naturally breaks into the following stories within the epic.

**Foundation**
- Story: Transcript ingestion with line numbering (Stage 0)
- Story: Project context and topic registry loader (Stage 1)
- Story: Gold set creation and evaluation harness (Stage 13)

**Recall layer**
- Story: Atomic unit extraction prompt + LLM call (Stage 2)
- Story: Adversarial recall pass (Stage 3)
- Story: Deterministic citation resolution from line refs (Stage 4)

**Organization layer**
- Story: Topic clustering with registry as preferred vocabulary (Stage 5)
- Story: Registry reconciliation and new topic queueing (Stage 6)

**Synthesis layer**
- Story: Per-topic task synthesis prompt + per-topic LLM calls (Stage 7)
- Story: Task-level citation attachment (Stage 8)

**Operational layer**
- Story: Confidence scoring heuristic (Stage 9)
- Story: Validation rules and failure handling (Stage 10)
- Story: Human review UI for new topics and low-confidence tasks (Stage 11)
- Story: Final output serialization to v4-compatible schema (Stage 12)

**Cross-cutting**
- Story: Logging and observability (model, params, timings, token counts per stage)
- Story: Registry persistence (storage, versioning, project scoping)
- Story: Retry and error handling policy across all LLM stages

---

## Open decisions

- **Confidence threshold for Stage 11 review**: initial value 0.5, tune against gold set.
- **Retry policy**: single retry on validation failure, or escalate immediately? Recommend single retry.
- **Registry storage**: same database as call-tracking app, or separate? Recommend same.
- **Per-topic LLM call parallelism in Stage 7**: parallel calls vs sequential? Parallel is faster but harder to debug. Recommend sequential initially, parallelize later if latency matters.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Stage 2 atomic extraction misses entire categories (e.g. all blockers) | Recall pass in Stage 3; gold-set evaluation in Stage 13 |
| Stage 5 misclusters domain-specific topics | Registry-as-vocabulary in prompt; human approval in Stage 11 |
| Per-topic synthesis in Stage 7 produces inconsistent task schemas | Strict JSON schema enforcement; validation in Stage 10 |
| Registry accumulates noise over time | Human approval gate; periodic registry review (out of pipeline scope) |
| Transcripts exceed Opus 4.7 context window | Out of scope; additive hierarchical chunking layer can be added before Stage 2 without rearchitecture |
| Pipeline latency exceeds acceptable bound | Stage 7 parallelization; LLM call batching where API supports it |

---

## Success criteria

The pipeline is considered shipped when, against the gold set:
- Topic recall ≥ 0.95
- Citation validity rate = 1.00
- Naming stability across 5 re-runs of the same transcript = 1.00
- Confidence scores correlate with human judgment at r ≥ 0.7
- Every stage has logging sufficient to reconstruct any single run's behavior