# EPIC-20 — Three-stage call processing: Topic confirmation → Task grouping → Project updates

**Status:** Brainstorm — awaiting design lock
**Date:** 2026-05-26
**Branch (target):** TBD (off `main` after EPIC-19 lands)
**Predecessor:** EPIC-19 (task-level matching) — superseded by this design

---

## 1. Motivation

EPIC-19 collapsed topic-level matching into a single screen where the user simultaneously decides:
- Which topics are still alive in this call
- Which call tasks group together
- Which existing project tasks each new task binds to

This works but is slow. The user reported "it takes too much time for me to group them together and match with previous topics" — three concerns mashed into one screen, no constraint reduction, every decision is freeform N:M.

**Insight:** these three concerns are sequential, not simultaneous. Decide topics FIRST, then place tasks under topics, then run synthesis. Each stage constrains the next, which makes the LLM's job tractable (v5 pattern: LLM does cognitive work in a narrow lane, code does the mechanical work, user audits at fast natural break points).

---

## 2. Three-stage architecture

### Stage 1 — Topic confirmation (NEW kanban stage)

**Goal:** produce the finalized topic list for this call.

**Inputs:**
- Existing project topics from `project_topic_state` view
- New-topic candidates emitted by v5 Stage 5 (clusters labeled `new_topic: true`)

**User actions:**
- Keep / rename / merge / drop each existing project topic
- Accept / rename / merge-with-existing each new-topic candidate
- Introduce a brand-new topic by hand (escape hatch)

**Output:**
A canonical list of topics for this call. Each entry tagged `existing(topic_id)` or `new(name)`.
- Topics IN the list = alive for this call going forward
- Topics NOT in the list (previous-call topics the user dropped) = **archived**

**Archiving rule (user-stated):** "if a topic isn't preserved on a new call, it wasn't a coherent topic." No safety net at this stage — the user owns the lifecycle decision.

---

### Stage 2 — Task grouping (current matching screen, refactored)

**Goal:** every task (previous-call + new-call) lives in exactly one group; every group lives under exactly one finalized topic.

**Inputs:**
- Finalized topic list from Stage 1
- Previous-call tasks for each kept topic (from `project_topic_state.tasks`)
- New-call atomic tasks from v5 Stage 4

**LLM auto-pass (server-side, fires on entry to Stage 2):**
1. Cluster tasks (old + new together) into small cohesive groups based on task-text similarity
2. For each group, propose one target topic from the finalized list

The LLM's job has become narrow and concrete:
- Input scope: a fixed list of topics + a fixed list of tasks
- Output: groups + topic assignments
- No verdict scoring, no rarity checks, no confidence math. Just cohesion + routing.

**User actions:**
- Drag any task between groups
- Drag a whole group from one topic to another
- Create a new group from one or more "ungrouped" orphan tasks
- Inline-edit topic names (syncs back to Stage 1's finalized list)
- Delete a group (its tasks return to the orphan bin)

**Orphan handling:**
- Tasks the LLM doesn't cluster sit in an "Ungrouped" bin at the top of Stage 2
- User must drop every orphan into a group before advancing to Stage 3
- Advancement is gated: cannot enter Stage 3 with non-empty orphan bin

**Output:**
For each finalized topic, a set of groups. Each group is one of three shapes:
- **New-only**: only new-call tasks → routed to Pass 1
- **Old-only**: only previous-call tasks → routed to Pass 2
- **Mixed**: both → routed to Pass 3

Old-only groups appear naturally — if a topic is kept at Stage 1 but the LLM didn't route any new tasks into it, its previous-call tasks form old-only groups (one per coherent sub-cluster, or one big bag — see open question #1).

---

### Stage 3 — Project updates (current 3-pass, routed by group composition)

**Pass routing (semantics, no `X:0` / `0:X` labels):**
- New-only group → **Pass 1** (`verify_new`) — "is this really a new task or already covered?"
- Old-only group → **Pass 2** (`verify_not_discussed`) — "this previous-call task wasn't discussed this call — confirm still holds, no progress"
- Mixed group → **Pass 3** (`synthesize_merged_topic`) — "given these previous + new tasks, produce the new state"

Passes can run in parallel across groups since each is self-contained.

**Output:** one row per group in `topic_updates`, keyed by group ID.

---

## 3. Data model changes

**New table or column to represent finalized topics per call:**
- Could be a JSON column on `calls` table: `finalized_topics jsonb` with entries `[{topic_id, name, is_new, source_v5_cluster_id}]`
- Or a dedicated `call_finalized_topics` table — preferred if we want history / audit

**`topic_match_groups` schema update:**
- Each group references exactly ONE target topic (kill the multi-topic primary-target hack from EPIC-19)
- Each task lives in exactly one group (drop the duplicate-tracking we built)
- Add `kind` enum: `new_only` | `old_only` | `mixed` (computed but persisted for routing simplicity)
- Drop `target_topic_name` (folded into the finalized topic record)

**Kanban stage advancement:**
- Add new stage between `call_topics` and `project_matching`: `topic_confirmation`
- Stages become: `extract` → `call_topics` → `topic_confirmation` → `task_grouping` (renamed from project_matching) → `project_updates` → `artifacts`

---

## 4. What gets deleted

- EPIC-19's multi-topic primary-target logic in `ProjectUpdatesStage.tsx`
- The drag-to-section-2 / drag-to-section-3 plumbing we just added (replaced by drag-within-Stage-2)
- The "no group → fallback to legacy untouched topic card" path (every alive topic is in the finalized list explicitly)
- 0:X / X:0 / M:N label semantics (replaced with `new_only` / `old_only` / `mixed`)

---

## 5. What stays from EPIC-18 / EPIC-19

- v5 atomic-task pipeline — **no change**. Output feeds Stage 1 (topic candidates) and Stage 2 (tasks to group).
- Pass 1 prompt (`verify_new`) — applied per group instead of per topic
- Pass 2 line-number citation pattern (ADR-004)
- Pass 3 synthesis prompt
- `project_topic_state` view (input to Stage 1)
- Color-coded group visualization

---

## 6. UX flow (end-to-end)

```
[Call uploaded] → v5 extracts atomic tasks + Stage 5 clusters under candidate topics
        ↓
[Stage 1 — Topic confirmation card]
    Two columns: existing project topics (left) | v5 new-topic candidates (right)
    User clicks through, archives dead topics, accepts new ones, merges where needed
    Output: finalized topic list
        ↓
[Stage 2 — Task grouping card]
    On entry: LLM auto-pass clusters all tasks (old + new), proposes target topics
    Display: one column per finalized topic, groups stacked inside, "Ungrouped" bin at top
    User drags to fix LLM mistakes, creates new groups for orphans
    Cannot advance while orphan bin is non-empty
        ↓
[Stage 3 — Project updates card]
    Three passes fire in parallel by group composition
    Each group produces one topic_updates row
    Current 3-pass UX preserved (per-group verdict cards, accept/reject)
        ↓
[Artifacts]
```

---

## 7. LLM passes summary

| Pass | When | Input | Output | Asymmetry |
|---|---|---|---|---|
| **v5 Stage 5** | Existing (unchanged) | Atomic tasks + project topic registry | Clusters with `new_topic` flag | n/a |
| **Stage 2 cluster** | NEW | Finalized topics + all tasks | Groups + target-topic-per-group | Wrong group = drag fix (cheap) |
| **Pass 1** (verify_new) | Stage 3, new-only groups | Group tasks + transcript | "really new" verdict + confidence | Wrong = reversible (re-route) |
| **Pass 2** (verify_not_discussed) | Stage 3, old-only groups | Group tasks + transcript | "still holds" verdict + citations | Wrong = reversible (mark as discussed) |
| **Pass 3** (synthesize) | Stage 3, mixed groups | Group tasks + previous topic_updates + transcript | New topic_updates row | Wrong = audit + rewrite (more work) |

---

## 8. Open questions

1. **Old-only groups per topic — one big bag or LLM-clustered?**
   When a kept topic has 8 previous-call tasks and zero new traction, do we form one old-only group containing all 8, or does the Stage 2 LLM cluster them into 2-3 sub-groups? Argument for one-bag: Pass 2 is per-group, so 8-tasks-in-one-bag means one Pass 2 call instead of 3. Argument for sub-clustering: if the user drags a new task into one sub-cluster, only that sub-cluster becomes mixed (Pass 3 input is narrower). **Lean: one-bag for simplicity; user can split manually if needed.**

2. **Stage 2 LLM scope per topic or global?**
   Option A: one LLM call per topic ("here are the tasks routed to this topic, cluster them"). Option B: one LLM call for the whole call ("here are all topics + all tasks, cluster + route in one shot"). Option B is one less round-trip but a much wider prompt. **Lean: B, with topic list as a fixed enum the LLM must pick from.**

3. **Stage 1 inline-edit propagation:**
   If the user renames a topic at Stage 1, does it propagate to `topic_registry` immediately (affecting the canonical name across the whole project), or only to this call's finalized list? **Lean: immediate propagation — the rename is an edit, not a per-call alias.**

4. **Re-running Stage 2's LLM auto-pass:**
   If the user goes back to Stage 1 and adds a new topic mid-flow, should Stage 2's groups be re-computed (LLM re-runs), or do the existing groups stay and only the new topic appears empty? **Lean: keep existing groups; only re-run if user explicitly clicks "Re-cluster".**

5. **Persistence of LLM proposals before user accepts:**
   Does Stage 2's LLM output persist immediately to `topic_match_groups`, or sit in a draft state until the user explicitly saves? **Lean: persist immediately (draft mode, same pattern as current task matching).** User edits mutate the persisted rows.

6. **Stage 1 UI shape:**
   Two columns (existing | new) with simple keep/drop toggles? Or a more sophisticated merge/split graph view? **Lean: start with two columns + simple actions; iterate if user needs more power.**

---

## 9. Phasing recommendation

Suggest a 4-phase plan:

- **Phase 1 — Data model & migration:** new `call_finalized_topics` table (or column), schema update to `topic_match_groups`, migration script for existing calls
- **Phase 2 — Stage 1 (Topic confirmation) backend + UI:** new kanban stage, two-column UI, persistence
- **Phase 3 — Stage 2 (Task grouping) refactor:** new LLM cluster+route pass, refactor existing screen to consume finalized topics, drag-within-stage UX
- **Phase 4 — Stage 3 wiring + smoke:** route 3 passes by group composition; remove dead EPIC-19 plumbing; smoke against project a + project b

Each phase is independently shippable behind a feature flag if needed.

---

## 10. Decisions locked (from this conversation)

- ✅ Three stages, sequential, separate kanban cards
- ✅ Topic archiving is user-driven at Stage 1 (no auto-preserve)
- ✅ Drag-and-drop UX at Stage 2: tasks between groups, groups between topics
- ✅ LLM proposes target topic per group; user can change
- ✅ Inline-edit topic names at Stage 2 (syncs back to Stage 1)
- ✅ Orphan bin: ungrouped tasks must be placed before advancing to Stage 3
- ✅ Pass routing by group composition (new-only / old-only / mixed)
- ✅ Drop `X:0` / `0:X` label conventions; use semantic names

---

## Next step

User reviews this brainstorm. If approved, run `superpowers:writing-plans` against it to produce `2026-05-26-epic-20-implementation-plan.md`.
