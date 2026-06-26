# EPIC-21 — Pipeline Collapse: Single Agentic Recap Pass

**Status:** Brainstorm (design approved, pending spec review)
**Date:** 2026-06-24
**Branch:** `epic-16-rag-rework`
**Supersedes:** the post-extraction stages of EPIC-19 / EPIC-20

---

## 1. The realization that drives this

The user reverse-engineered the *entire app* into a single Claude-chat workflow — and it beats the app at the core job (recap this call given the prior project state). The proof lives in `/Users/louisgarnier/Downloads/files3/`:

- `New_Project_Tracker_Starter_Prompt.md` — the methodology made explicit (EXTRACT → MATCH → VERIFY → APPLY, topic rules, anchor objects, honesty requirements, output spec).
- `tracker_v06.json` — the **lodestar**: 7 calls processed for SWIB × FactSet, 16 topics, structured anchors. This is the output quality we are targeting.
- `FactSet_SWIB_RAM_Tracker_v06.xlsx` — the 6-sheet Excel render.

**Why the chat wins:** it runs MATCH/VERIFY/APPLY in *one reasoning context* that sees the full transcript **and** the full prior tracker at once. The app splits the same logic across many stages, each operating on the *previous stage's degraded output*. Decomposition was meant to improve reliability; instead each stage sheds signal and the user has been hand-correcting compounding errors.

**The corrections the user makes by hand are rule-shaped** (merged two topics that aren't the same, dropped a task, treated a side comment as a decision) — i.e. catchable by an automated critic, not requiring human taste. This is already written down as the "honesty requirements" in the starter prompt.

**Root cause, stated plainly:** the pipeline never had an *agentic pass* — a step that reasons over the full picture in one context and self-corrects against the rules before committing. It only had single-shot prompts, each firing once on a fragment with no feedback loop. The chat *is* agentic by default (the user reads the draft, corrects, the model revises) and that is the entire reason it wins. **The missing agentic pass is the key cause of the quality problems we've had until now** — not the prompts themselves, not the model, not the schema. Re-introducing that pass is the load-bearing change of EPIC-21; everything else (keeping v5, persistence, Excel render) is supporting structure.

## 2. What the app is actually for

A plain chat can do the reasoning. The app earns its existence only by doing what a chat cannot:

1. **Hold the standard** — methodology + schema + glossary, so the user never re-pastes their expectations.
2. **Persist & accumulate** — prior project state is stored and auto-fed into the next call. The chat forgets; the app accumulates across N calls.
3. **Standardized output** — guaranteed schema, no per-call fine-tuning of format.
4. **Render & version** — auto-produce the Excel, keep versioned snapshots.

The app stops being "the thing that reasons" and becomes "the thing that remembers the standard and the history, and runs the proven prompt."

## 3. Goals

- Match the lodestar (`tracker_v06.json`) output quality on real project data.
- Collapse the multi-stage post-extraction pipeline into **one agentic MATCH→VERIFY→APPLY pass** that sees the full prior state at once.
- Keep the proven v5 extraction engine untouched.
- Encode the user's methodology + honesty rules once, globally; carry per-project context (glossary/parties/role).
- Surface low-confidence decisions for user confirmation — never auto-apply silently.

## 4. Non-goals (LAW)

- **Do NOT touch the v5 extraction orchestrator.** Its output is good; treat it as a black box.
- Do NOT re-introduce topic-level verification, rarity checks, or the sanity-flag stack (obsoleted in EPIC-19).
- Do NOT build per-project *standards* — the methodology/schema/output format is global. Only context (glossary etc.) is per-project.
- Do NOT auto-close or silently merge topics.

## 5. Architecture

```
  Transcript
      │
      ▼
┌─────────────────────────┐
│  v5 orchestrator         │   KEEP — untouched black box
│  (call_topics stage)     │   → clean topic list for THIS call
└─────────────────────────┘
      │  extracted topics
      ▼
┌──────────────────────────────────────────────────────────┐
│  AGENTIC RECAP PASS  (the rework)                          │
│  Inputs, all in one context:                               │
│   • new call's extracted topics (from v5)                  │
│   • FULL prior project state (every topic + anchors +      │
│     decisions + open questions + expected next steps)      │
│   • per-project glossary / parties / role                  │
│   • global methodology + schema + honesty rules            │
│  Does: MATCH (extend vs new) → VERIFY (cross-check prior   │
│   decisions & next steps against transcript) → APPLY       │
│   (produce updated state)                                  │
│  Self-critiques against honesty rules; flags low-          │
│   confidence items for user confirmation.                  │
└──────────────────────────────────────────────────────────┘
      │  updated project state + flagged items
      ▼
┌─────────────────────────┐
│  App responsibilities    │
│  • persist new state      │
│  • version snapshot       │
│  • render 6-sheet Excel   │
│  • UI: confirm flagged    │
└─────────────────────────┘
```

### 5.1 Keep, untouched
- `backend/services/call_topics_v5/orchestrator.py` (`run_pipeline`) and its prompts. Extraction front-end. Output = clean topics from the transcript.

### 5.2 The rework — one agentic pass
Replaces the logic currently spread across: `topic_confirmation`, `project_matching`, `task_grouping`, and the `project_updates` 3-pass synthesis.

- **Full prior context is non-negotiable.** The pass must receive, in one context:
  - **previous call transcripts** for the project (the raw source — needed for the VERIFY step's "sanity-check against prior transcripts to confirm it's the same thread");
  - **all previous topics and their full update history** — every topic with its anchors, decisions, open questions, expected next steps, and per-call `updates`.
  This is so it can genuinely follow up on open items and cross-check past decisions / expected next steps against what was actually said. The app's failure was never about storage location — it was that no step ever saw the whole prior state *and* the prior transcripts at once.

- **Transcript recency window (memory maturation).** Raw transcripts do *not* need to be fed forever. Recent calls stay raw because their threads are still forming and need source-level cross-checking; older calls have matured into clean, clarified topics/follow-ups, so the **distilled tracker state becomes the reliable record** and the raw transcript adds noise. Design: feed full transcripts for the most recent **N calls** (working assumption **N ≈ 5–7**, i.e. by ~call 10 the earliest calls drop to distilled-only), and rely on the topics/anchors/updates for everything older. N is a tunable, not a hard rule. This also keeps context cost bounded as call count grows.
- **v5 output already arrives in tracker shape — APPLY is a reconcile/merge, not a rebuild.** The call_topics stage already emits one structured row per topic with `name`, `key_terms`, `current_summary`, `next step`, `owner`, `status`, `open_questions`, and `decisions` — i.e. the same anchor-object structure as `tracker_v06.json`, just for a single call. The agentic pass therefore does **not** restructure raw topics into a schema; it takes these already-structured per-call topics and reconciles them into the accumulated multi-call tracker: match each to an existing thread or mark it new, carry forward / close the right anchors, verify status changes against the transcript, and append the per-call `update`. The implementation plan must map v5's output fields straight onto the tracker topic schema (including `next step` / `owner`, which v5 surfaces as first-class columns) rather than re-deriving them.

- **Self-critique loop** built from the honesty rules: surface every match decision (which existing topic + why), flag low-confidence rather than guessing, ASK when continuation-vs-new is genuinely ambiguous, never auto-close. The user's hand-corrections are rule-shaped, so this critic closes most of the gap automatically.
- **Human-in-the-loop is core, not optional.** After the pass produces the updated recap, the user can **edit it directly** — move topics/tasks around, rename, merge/split, correct anchors — using the same editing affordances available today. A **Validate button** locks the result; only validated state becomes the trusted prior state for the next call. The pass proposes; the user disposes.
- **Never invent — when unsure, leave it out.** Omission always beats fabrication. Zero invented items, ever — no decision, follow-up, owner, status, or topic that isn't grounded in the transcript. When the model is uncertain, it must **abstain (omit + flag)** rather than guess. This is also the practical answer to confidence calibration: bias the pass toward leaving things out and surfacing them for the user, never toward confidently filling gaps.
- **Drop-out protection.** Two mechanisms limit topics silently vanishing: (a) v5 extraction keeps each call's output stable and similarly-shaped, and (b) the pass cross-checks prior transcripts for existing tasks/topics. On top of these, a cheap validation assert (every prior topic is either carried forward, explicitly closed, or marked "Not raised" — never dropped) acts as a safety net.

### 5.3 App responsibilities
- Persist updated project state and version it (mirror of `tracker_vN` progression).
- Render the 6-sheet Excel (Dashboard, Chronology, Anchors lifecycle, Decisions log, Key terms registry, Status review) — the EPIC-15 Phase 2 tracker/Excel vision, now proven viable by the chat.
- Store the global methodology/schema and the per-project context (glossary/parties/role).

### 5.4 Storage
Functionally file-vs-table is equivalent; keep state in the DB (tables already exist). The hard requirement is that the **complete** prior state is assembled and fed to the pass each call — not the medium it sits in.

## 6. Data shape (the standard)

Global schema mirrors `tracker_v06.json`. Per topic: `id`, `name`, `created_in_call`, `last_updated_in_call`, `status` (open/closed), `importance`, `is_parked`, `key_terms`, `current_summary`, plus **anchor objects**:
- `decisions: [{text, decided_in}]`
- `follow_up_items: [{text, owner, added_in, status, closed_in}]`
- `open_questions: [{text, added_in, status, resolved_in}]`
- `updates: [{date, summary}]` — one per call, "Not raised" if untouched
- `rag_grounding_notes` — match/status reasoning

Per-project context: name, role, main parties, known workstreams, glossary (10-20 terms).

## 7. Testing

The bar is **not** exact reproduction of `tracker_v06.json` — v06 took 7 calls of human correction to reach its quality, and the pass won't (and shouldn't) match it one-shot. Instead:

- **The tool must learn, not just run a fixed prompt — but learning is split along two strictly separate axes:**
  - **Content / project state → per-project, never crossed.** Each project's calls, topics, decisions, and glossary are siloed. Project A's content must never leak into Project B; they have different goals and subject matter. Within a project, the pass grounds each call in the **accumulated, user-validated prior state**, so it gets better-grounded as that project matures. This is automatic from persistence + the Validate button.
  - **Technical machinery (the "architecture of the work") → global, improves across projects.** Improvements to *how* extraction/matching/verification work — heuristics, process discipline, prompt structure — are project-agnostic and SHOULD benefit every project. A matching improvement discovered while running Project A applies to Project B.
  - **The wall between them is absolute:** mechanism is shared; content is never shared. This is precisely why it must be agentic rather than a hardcoded prompt — the machinery can evolve while content stays siloed.
- **Concrete acceptance bar** (the test oracle): no topic wrongly merged, no open follow-up lost, every status change grounded in the transcript, and **zero invented items**. v06 is the reference for *shape and methodology quality*, used to sanity-check the pass's output — not a string-match target.
- The methodology doc's "Test 5 — does the loop hold for one more call?" framing applies: coherence must survive to call 5+.

## 8. What gets removed / obsoleted

The downstream stages collapsed into the single pass: `topic_confirmation`, `project_matching`, `task_grouping`, `project_updates` 3-pass. Their routers, services, prompts, and kanban wiring are candidates for removal once the pass matches the lodestar. (Exact removal list to be enumerated in the implementation plan — do not delete before the pass is proven.)

## 9. Open questions for the implementation plan

- New simplified kanban stage layout: `transcript → call_topics (v5) → recap (agentic pass + confirm) → done`? Confirm stage names/flow.
- How flagged/low-confidence items are presented in the UI (inline confirm vs review queue).
- Migration path for existing projects already carrying EPIC-19/20 state.
- Where the global methodology/schema lives (artifact library entry vs config file).
- Exact transcript recency window `N` (working assumption 5–7) and whether it's fixed, configurable per project, or adaptive to topic maturity.

## 10. Locked decisions (from this brainstorm)

1. v5 extraction stays untouched (black box, output is good).
2. Everything after extraction collapses into one agentic pass that sees full prior state.
3. Self-critique against the honesty rules; corrections are rule-shaped, so this is automatable.
4. Low-confidence items are confirmed by the user, never auto-applied.
5. Methodology/schema/output is global; only context (glossary/parties/role) is per-project.
6. Lodestar = `tracker_v06.json` — reference for *shape and methodology quality*, not a string-match target. Acceptance bar: no topic wrongly merged, no open follow-up lost, every status change grounded in the transcript, zero invented items.
7. Raw transcripts are fed only for the most recent N calls (memory maturation); older calls rely on distilled topics/anchors/updates. Exact N tuned in the plan.
8. Human-in-the-loop is core: the user edits the post-pass output (same affordances as today) and a Validate button locks it; only validated state becomes trusted prior state.
9. Never invent — when unsure, omit and flag for the user, never fabricate. Omission always beats fabrication.
10. Two-axis learning with an absolute wall: project **content/state is siloed per-project and never crossed**; the **technical machinery (extraction/matching/verification) is global and improves across projects**.
